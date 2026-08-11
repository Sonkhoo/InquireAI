"""
Qdrant handles:
    1. Dense embedding generation using Qwen
    2. Sparse embedding generation
    3. Vector storage

The application only sends chunk text to Qdrant.

RBAC metadata is stored in the Qdrant payload and enforced during
retrieval-time filtering.
"""

from __future__ import annotations

import logging
import os
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse,
)
from qdrant_client.models import Document, PointStruct
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from app.logging import logfire
from app.models import Chunk, ChunkMetadata
from app.config import get_settings

settings = get_settings()
# model configurations 

QDRANT_URL = settings.QDRANT_URL
QDRANT_API_KEY = settings.QDRANT_API_KEY
COLLECTION_NAME = "documents"
DENSE_MODEL = settings.dense_model
SPARSE_MODEL = settings.sparse_model
DENSE_DIM = 2560  
MAX_STORE_RETRIES = 3
UPSERT_BATCH_SIZE = 64

# error classes for retryable vs terminal failures
class StoreError(Exception):
    """Base class for vector storage failures."""


class RetryableStoreError(StoreError):
    """Transient Qdrant failure. Safe to retry."""


class TerminalStoreError(StoreError):
    """Non-retryable Qdrant failure."""


_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    """
    Lazy singleton Qdrant client.

    Keeping this lazy prevents Qdrant connections from being created
    during module import.
    """
    global _client

    if _client is None:
        _client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            cloud_inference=True,
        )
    return _client


def ensure_collection(client: QdrantClient) -> None:
    """
    Create the Qdrant collection and required payload indexes.

    The collection contains:

        dense  -> Qwen semantic embedding
        sparse -> sparse lexical representation

    """

    client = client or _get_client()

    try:
        exists = client.collection_exists(
            collection_name=COLLECTION_NAME
        )

    except (
        ResponseHandlingException,
        UnexpectedResponse,
    ) as exc:
        raise RetryableStoreError(
            f"store.py: could not reach Qdrant: {exc}"
        ) from exc

    if not exists:
        logfire.info(
            "store.py: creating Qdrant collection",
            collection=COLLECTION_NAME,
            dense_model=DENSE_MODEL,
            sparse_model=SPARSE_MODEL,
            dense_dim=DENSE_DIM,
        )

        client.create_collection(
            collection_name=COLLECTION_NAME,

            # Dense named vector
            vectors_config={
                "dense": qmodels.VectorParams(
                    size=DENSE_DIM,
                    distance=qmodels.Distance.COSINE,
                    hnsw_config=qmodels.HnswConfigDiff(
                        m=16,  # Balanced connections (default)
                        ef_construct=200,  # Good build quality (default)
                        full_scan_threshold=10000,  # Use brute force below this size (default)
                    ),
                ),
            },

            # Sparse named vector
            sparse_vectors_config={
                "sparse": qmodels.SparseVectorParams(
                    modifier=qmodels.Modifier.IDF,
                )
            },
        )

    #Create payload indexes for filtering
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="workspace_id",
        field_schema=qmodels.PayloadSchemaType.KEYWORD,
    )

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="allowed_role_ids",
        field_schema=qmodels.PayloadSchemaType.KEYWORD,
    )

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="file_id",
        field_schema=qmodels.PayloadSchemaType.KEYWORD,
    )


def _chunk_to_point(chunk: Chunk) -> PointStruct:
    """
    Convert an enriched Chunk into a Qdrant PointStruct.

    No embeddings are generated in Python.

    Instead, Document(text=..., model=...) tells Qdrant's inference
    layer to generate the vectors.
    """

    meta = chunk.metadata
    if not isinstance(meta, ChunkMetadata):
        raise TerminalStoreError(
            f"store.py: chunk.metadata is not a ChunkMetadata instance: {type(meta)}"
        )
    
    return PointStruct(
        id=chunk.id,

        vector={
            "dense": Document(
                text=chunk.text,
                model=DENSE_MODEL,
            ),
            "sparse": Document(
                text=chunk.text,
                model=SPARSE_MODEL,
            ),
        },

        payload={
            "workspace_id": meta.workspace_id,
            "allowed_role_ids": meta.allowed_role_ids,
            "file_id": meta.file_id,
            "filename": meta.filename,
            "chunk_index": meta.chunk_index,
            "page_start": meta.page_start,
            "page_end": meta.page_end,
            "section_title": meta.section_title,
            "token_count": meta.token_count,
            "text": chunk.text,
            "context_summary": getattr(
                chunk,
                "context_summary",
                None,
            ),
        },
    )

@retry(
    retry=retry_if_exception_type(RetryableStoreError),
    stop=stop_after_attempt(MAX_STORE_RETRIES),
    wait=wait_exponential(
        multiplier=1,
        min=2,
        max=30,
    ),
    before_sleep=before_sleep_log(
        logging.getLogger(__name__),
        logging.WARNING,
    ),
    reraise=True,
)
def _upsert_batch(
    client: QdrantClient,
    points: List[PointStruct]
) -> None:
    """
    Upload one batch to Qdrant.

    Qdrant performs the dense + sparse inference while processing
    these points.
    """

    try:
        client.upload_points(
            collection_name=COLLECTION_NAME,
            points=points,
            batch_size=UPSERT_BATCH_SIZE,
            wait=True,
        )

    except ResponseHandlingException as exc:
        raise RetryableStoreError(
            f"store.py: transient Qdrant error: {exc}"
        ) from exc

    except UnexpectedResponse as exc:

        status = getattr(
            exc,
            "status_code",
            None,
        )

        if status is not None and status >= 500:
            raise RetryableStoreError(
                f"store.py: Qdrant server error "
                f"({status}): {exc}"
            ) from exc

        raise TerminalStoreError(
            f"store.py: Qdrant rejected upsert: {exc}"
        ) from exc


# public API
def store_chunks(chunks: List[Chunk]) -> int:
    """
    Embed and store chunks in Qdrant.

    Qdrant generates:

        chunk.text
            ├──> dense Qwen embedding
            └──> sparse embedding

    Args:
        chunks:
            Output of the enrichment/chunking pipeline.

        client:
            Optional Qdrant client, primarily useful for testing.

    Returns:
        Number of chunks stored.
    """

    if not chunks:
        return 0

    client = _get_client()

    ensure_collection(client)

    logfire.info(
        "store.py: preparing chunks for Qdrant",
        count=len(chunks),
        dense_model=DENSE_MODEL,
        sparse_model=SPARSE_MODEL,
    )

    # Convert chunks to Qdrant points.
    points = [
        _chunk_to_point(chunk)
        for chunk in chunks
    ]

    total = len(points)

    # Upload in batches.
    for i in range(
        0,
        total,
        UPSERT_BATCH_SIZE,
    ):
        batch = points[
            i : i + UPSERT_BATCH_SIZE
        ]

        _upsert_batch(
            client,
            batch,
        )

        logfire.info(
            "store.py: uploaded batch",
            uploaded=min(
                i + UPSERT_BATCH_SIZE,
                total,
            ),
            total=total,
        )

    logfire.info(
        "store.py: vector storage complete",
        collection=COLLECTION_NAME,
        total=total,
    )

    return total