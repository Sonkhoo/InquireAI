from __future__ import annotations

from groq import Groq
from groq import APIStatusError, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
from docling_core.types.doc import DoclingDocument
import logging
from app.logging import logfire
from app.models import Chunk
from app.ingestion.chunk import tokenizer  # reuse the already-loaded Qwen3 tokenizer

"""
ai_core/ingestion/enrich.py

Pipeline step 9: contextual summarization.

For each chunk, generates a 1-2 sentence summary situating it within the
source document (Anthropic-style contextual retrieval), then prepends that
summary to chunk.text before embedding, and stores it separately on
chunk.metadata.context_summary (per the Qdrant payload shape: text + context_summary
as distinct fields).

ASSUMPTION: Chunk (app.models) has a `context_summary: str | None` field.
If it doesn't yet, add it -- chunk.py currently constructs Chunk without one.

Free-tier gating:
openai/gpt-oss-120b free tier is ~8,000 tokens/minute (TPM). A single call
carrying the full document as prefix must itself fit under that ceiling for
prompt caching to work at all (caching only discounts *repeat* calls, not
the first one). We gate on document token count -- computed with the same
Qwen3 tokenizer chunk.py already loads, as a proxy for the Groq token count
(different tokenizer, so treat DOC_TOKEN_THRESHOLD as a conservative
estimate, not an exact Groq token count).
"""

GROQ_MODEL = "openai/gpt-oss-120b"

# Conservative buffer under the ~8,000 TPM free-tier ceiling -- leaves room
# for the instruction wrapper, output tokens, tokenizer mismatch (Qwen3 vs
# Groq's own tokenizer), and other org traffic sharing the same rate-limit
# pool. Tune down further if you see 429s in practice.
DOC_TOKEN_THRESHOLD = 6000

MAX_ENRICH_RETRIES = 4

SYSTEM_PROMPT_TEMPLATE = """You are generating short context notes for chunks of a document, to improve retrieval in a search system.

You will be given the FULL DOCUMENT TEXT once, followed by individual chunks one at a time. For each chunk, write a 1-2 sentence summary that situates the chunk within the overall document -- what section or topic it belongs to, and how it relates to the document as a whole. Be concise and factual. Do not repeat the chunk's content verbatim, just provide the surrounding context.

Respond with only the 1-2 sentence context summary. No preamble, no labels, no quotation marks.

FULL DOCUMENT TEXT:
{document_text}"""

CHUNK_PROMPT_TEMPLATE = """Here is the chunk to situate within the document above:

<chunk>
{chunk_text}
</chunk>

Give a 1-2 sentence context summary for this chunk."""


# --- Errors -----------------------------------------------------------------
# Mirrors the retryable/terminal distinction used in parse.py.

class EnrichError(Exception):
    """Base class for enrichment failures."""


class RetryableEnrichError(EnrichError):
    """Transient failure (rate limit, timeout, connection issue) -- retry."""


class TerminalEnrichError(EnrichError):
    """Non-retryable failure (auth, bad request, etc.) -- do not retry."""


# --- Helpers ------------------------------------------------------------

def _is_retryable_groq_error(exc: APIStatusError) -> bool:
    # 429 and 5xx are worth retrying; 4xx auth/bad-request are not.
    return exc.status_code == 429 or exc.status_code >= 500


@retry(
    retry=retry_if_exception_type(RetryableEnrichError),
    stop=stop_after_attempt(MAX_ENRICH_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
    reraise=True,
)
def _call_groq_for_context(client: Groq, document_text: str, chunk_text: str) -> str:
    """Single per-chunk contextualization call.

    Static content (system prompt + full document text) goes first, dynamic
    content (the chunk) goes last -- required prefix ordering for Groq
    prompt caching to recognize repeat calls for the same document.
    """
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT_TEMPLATE.format(document_text=document_text),
                },
                {
                    "role": "user",
                    "content": CHUNK_PROMPT_TEMPLATE.format(chunk_text=chunk_text),
                },
            ],
            temperature=0.0,
            max_tokens=100,
        )
    except (RateLimitError, APIConnectionError, APITimeoutError) as exc:
        raise RetryableEnrichError(str(exc)) from exc
    except APIStatusError as exc:
        if _is_retryable_groq_error(exc):
            raise RetryableEnrichError(str(exc)) from exc
        raise TerminalEnrichError(f"Groq request failed ({exc.status_code}): {exc}") from exc

    summary = response.choices[0].message.content
    if not summary or not summary.strip():
        raise TerminalEnrichError("Groq returned an empty context summary")

    usage_details = getattr(getattr(response, "usage", None), "prompt_tokens_details", None)
    cached_tokens = getattr(usage_details, "cached_tokens", None) if usage_details else None
    if cached_tokens:
        logfire.info(f"Groq cache hit: {cached_tokens} cached input tokens")

    return summary.strip()


# --- Public API -----------------------------------------------------------

def enrich_chunks(
    dl_doc: DoclingDocument,
    chunks: list[Chunk],
    workspace_id: str,
    filename: str,
    client: Groq | None = None,
) -> list[Chunk]:
    """Contextual summarization for a document's chunks (pipeline step 9).

    Args:
        dl_doc: the DoclingDocument returned by parse.py -- used to derive
            the full document text via export_to_markdown(), same source
            chunk.py itself uses.
        chunks: output of chunk_document() -- context_summary not yet set.
        workspace_id, filename: for logging, matching chunk.py's convention.
        client: optional pre-built Groq client (mainly for testing);
            defaults to a fresh client reading GROQ_API_KEY from env.

    Returns:
        list[Chunk] -- same chunk objects, mutated in place: context_summary
        populated and text updated to f"{context_summary}\n\n{original_text}"
        for chunks that were enriched. If the document exceeds
        DOC_TOKEN_THRESHOLD, chunks are returned unmodified -- enrichment is
        skipped entirely rather than failing or partially degrading.
    """
    if not chunks:
        return chunks

    document_text = dl_doc.export_to_markdown()

    tokens = tokenizer(document_text)["input_ids"]
    doc_tokens = len(tokens)

    if doc_tokens > DOC_TOKEN_THRESHOLD:
        logfire.info(
            f"enrich.py: skipping contextual summarization for {filename} "
            f"(workspace_id={workspace_id}, ~{doc_tokens} tokens > threshold "
            f"{DOC_TOKEN_THRESHOLD}) -- doc exceeds free-tier TPM budget for "
            f"full-document caching; chunks proceed to embedding unenriched."
        )
        return chunks

    logfire.info(
        f"enrich.py: contextualizing {len(chunks)} chunks for {filename} "
        f"(workspace_id={workspace_id}, ~{doc_tokens} tokens)"
    )

    groq_client = client or Groq()

    for i, chunk in enumerate(chunks):
        try:
            summary = _call_groq_for_context(groq_client, document_text, chunk.text)
        except TerminalEnrichError as exc:
            logfire.error(
                f"enrich.py: terminal error on chunk {i}/{len(chunks)} "
                f"for {filename} (workspace_id={workspace_id}): {exc}"
            )
            continue
        except RetryableEnrichError as exc:
            logfire.error(
                f"enrich.py: exhausted retries on chunk {i}/{len(chunks)} "
                f"for {filename} (workspace_id={workspace_id}): {exc}"
            )
            continue

        chunk.metadata.context_summary = summary
        chunk.text = f"{summary}\n\n{chunk.text}"

    logfire.info(
        f"enrich.py: enrichment complete for {filename} "
        f"({sum(1 for c in chunks if c.metadata.context_summary)}/{len(chunks)} chunks enriched)"
    )

    return chunks