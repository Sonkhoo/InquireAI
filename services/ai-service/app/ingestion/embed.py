"""
This module embeds
"""

from __future__ import annotations

import os
from typing import List

from sentence_transformers import SentenceTransformer

from app.logging import logfire
from app.models import Chunk

"""
ai_core/ingestion/embed.py

Pipeline step: embedding.

Embeds each chunk's text using
Qwen3-Embedding-4B in-process via sentence-transformers, and fills
chunk.embedding.

Dimension note: Qwen3-Embedding-4B natively outputs 2560-dim vectors (MRL
supports truncating down to as low as 32, but we use the native 2560 here).
EMBED_DIM below MUST match the Qdrant collection's vector size configured
in store.py -- a mismatch fails at upsert time, not at import time, so
keep these two files' constants in sync if you ever change models/dims.

No query-side instruction prefix is applied here -- this module only
embeds *documents* (chunks). Qwen3-Embedding models recommend a
`prompt_name="query"` instruction prefix specifically for the query side
at retrieval time (chat.py / the query pipeline), not for document
embedding -- using the doc-side (uninstructed) encode() call here is
correct per the model card.
"""

EMBED_MODEL_ID = "Qwen/Qwen3-Embedding-4B"
EMBED_DIM = 2560  # must match store.py's Qdrant VectorParams(size=...)

# Local in-process inference, not an external API -- no tenacity retry here;
# a batch that OOMs will OOM again on retry. We catch and re-raise with a
# clearer message instead, and let the pipeline's own retry/failure handling
# (per parse.py's pattern) decide whether to retry the whole document.
DEFAULT_BATCH_SIZE = 16


class EmbedError(Exception):
    """Base class for embedding failures."""


class TerminalEmbedError(EmbedError):
    """Non-retryable failure (OOM, bad input, model load failure)."""


_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Lazy singleton -- avoids loading an 8GB model at import time for
    code paths (tests, other pipeline steps) that never call embed_chunks()."""
    global _model
    if _model is None:
        logfire.info(f"embed.py: loading {EMBED_MODEL_ID}")
        model = SentenceTransformer(EMBED_MODEL_ID)
        actual_dim = model.get_sentence_embedding_dimension()
        if actual_dim != EMBED_DIM:
            raise TerminalEmbedError(
                f"embed.py: EMBED_DIM={EMBED_DIM} does not match the model's "
                f"actual output dimension ({actual_dim}). Update EMBED_DIM "
                f"(and store.py's VectorParams size) to match."
            )
        _model = model
    return _model


def embed_chunks(
    chunks: List[Chunk],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> List[Chunk]:
    """Embed chunk.text for every chunk in place, filling chunk.embedding.
    Args:
        chunks: output of enrich_chunks() (or chunk_document() directly, if
            enrichment was skipped for a large doc) -- chunk.text is
            whatever should be embedded, chunk.embedding is currently None.
        batch_size: encode() batch size. Lower this if you hit OOM on
            longer documents or a memory-constrained machine.
    Returns:
        The same list, with chunk.embedding populated per chunk.
    """
    if not chunks:
        return chunks

    model = _get_model()
    texts = [c.text for c in chunks]

    logfire.info(f"embed.py: embedding {len(texts)} chunks (batch_size={batch_size})")

    try:
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    except RuntimeError as exc:
        # Most commonly CUDA/CPU OOM on a large batch or long document.
        raise TerminalEmbedError(
            f"embed.py: encode() failed ({exc}). If this is an OOM, try "
            f"reducing batch_size (currently {batch_size})."
        ) from exc

    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector.tolist()

    logfire.info(f"embed.py: embedding complete for {len(chunks)} chunks")

    return chunks