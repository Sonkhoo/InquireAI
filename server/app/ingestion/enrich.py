from __future__ import annotations
import time

from groq import Groq
from groq import APIStatusError, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
from docling_core.types.doc.document import DoclingDocument
import logging
from app.logging import logfire
from app.models import Chunk, ChunkMetadata
from app.ingestion.chunk import hf_tokenizer  # reuse the already-loaded Qwen3 tokenizer
from app.llm import get_groq_client, get_primary_model

"""
ai_core/ingestion/enrich.py

Pipeline step 9: contextual summarization.

For each chunk, generates a 1-2 sentence summary situating it within the
source document (Anthropic-style contextual retrieval), then prepends that
summary to chunk.text before embedding, and stores it separately on
chunk.metadata.context_summary (per the Qdrant payload shape: text + context_summary
as distinct fields).

"""
GROQ_MODEL = get_primary_model()


DOC_TOKEN_THRESHOLD = 6000

MAX_ENRICH_RETRIES = 3

SYSTEM_PROMPT_TEMPLATE = """You are a contextual retrieval assistant.

Your ONLY task is to generate a short context description for the supplied chunk.

The full document below is provided ONLY so you can understand where the chunk belongs.

RULES:
- Output exactly 1 or 2 COMPLETE sentences.
- Output approximately 20-50 words.
- Identify the section/topic the chunk belongs to when possible.
- Explain how the chunk relates to the surrounding document.
- Be factual and concise.
- Do not summarize the entire document.
- Do not repeat the chunk verbatim.
- Do not output bullets.
- Do not output labels.
- Do not output explanations.
- NEVER return an empty response.

FULL DOCUMENT:
{document_text}
"""

CHUNK_PROMPT_TEMPLATE = """Now contextualize ONLY this chunk:

<chunk>
{chunk_text}
</chunk>

Return ONLY the 1-2 sentence context description."""


# --- Errors -----------------------------------------------------------------

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
            reasoning_effort="low",
            temperature=0.0,
            max_tokens=200,
        )
        message = response.choices[0].message
        usage = getattr(response, "usage", None)
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

    tokens = hf_tokenizer(document_text)["input_ids"]
    doc_tokens = len(tokens)

    if doc_tokens > DOC_TOKEN_THRESHOLD:
        return chunks

    logfire.info(
        f"enrich.py: contextualizing {len(chunks)} chunks for {filename} "
        f"(workspace_id={workspace_id}, ~{doc_tokens} tokens)"
    )

    groq_client = get_groq_client()

    for i, chunk in enumerate(chunks):
        if chunk.text.strip() == "<!-- image -->":
            continue
        try:
            logfire.info(
                "enrich_chunk_start",
                chunk_index=i,
                chunk_chars=len(chunk.text),
            )
            start_time = time.perf_counter()
            summary = _call_groq_for_context(groq_client, document_text, chunk.text)
            elapsed_time = time.perf_counter() - start_time
            logfire.info(
                "enrich_chunk_complete",
                chunk_index=i,
                elapsed_ms=elapsed_time * 1000,
                summary_length=len(summary),
            )
        except TerminalEnrichError as exc:
                logfire.error(
                    f"enrich.py: terminal error on chunk {i}/{len(chunks)} "
                    f"for {filename} (workspace_id={workspace_id}): {exc}"
                )
                raise
        except RetryableEnrichError as exc:
                logfire.error(
                    f"enrich.py: exhausted retries on chunk {i}/{len(chunks)} "
                    f"for {filename} (workspace_id={workspace_id}): {exc}"
                )
                raise

        chunk.metadata.context_summary = summary
        chunk.text = f"{summary}\n\n{chunk.text}"
    logfire.info(
        f"enrich.py: enrichment complete for {filename} "
        f"({sum(1 for c in chunks if c.metadata.context_summary)}/{len(chunks)} chunks enriched)"
    )

    return chunks