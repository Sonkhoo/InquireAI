"""
Query-time hybrid retrieval: dense (Jina v4) + sparse (BM25) + RRF fusion,
with RBAC enforced as part of the same Qdrant query (not post-hoc).
"""

from __future__ import annotations

from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Document, PointStruct
from qdrant_client.http import models as qmodels
from typing import Union
from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
import logging
from app.models import RetrievedChunk
from app.logging import logfire
from app.config import get_settings
from app.db.store import (
    _get_client
)
from app.retrieval.reranker import rerank_chunks
from app.retrieval.synthesizer import synthesize_response
from app.retrieval.confidence import compute_confidence
settings = get_settings()

JINA_API_KEY = settings.JINA_API_KEY
COLLECTION_NAME = "documents"
DENSE_MODEL = settings.dense_model
SPARSE_MODEL =  settings.sparse_model
DENSE_DIM = 1024  

PREFETCH_LIMIT = 5
DEFAULT_LIMIT = 3
MAX_SEARCH_RETRIES = 3


class HybridSearchError(Exception):
    """Base class for hybrid search failures."""


class RetryableSearchError(HybridSearchError):
    """Transient Qdrant failure. Safe to retry."""


@retry(
    retry=retry_if_exception_type(RetryableSearchError),
    stop=stop_after_attempt(MAX_SEARCH_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(
        logging.getLogger(__name__),
        logging.WARNING,
    ),
    reraise=True,
)
def _query_points(client: QdrantClient, prefetch, limit: int):
    try:
        return client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=prefetch,
            query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
    except ResponseHandlingException as exc:
        raise RetryableSearchError(
            f"hybrid.py: transient Qdrant error: {exc}"
        ) from exc
    except UnexpectedResponse as exc:
        status = getattr(exc, "status_code", None)
        if status is not None and status >= 500:
            raise RetryableSearchError(
                f"hybrid.py: Qdrant server error ({status}): {exc}"
            ) from exc
        raise


def _to_retrieved_chunk(point: qmodels.ScoredPoint) -> RetrievedChunk:
    """Convert a Qdrant ScoredPoint to a RetrievedChunk for downstream
    consumption.

    Args:
        point: Qdrant ScoredPoint from query_points response.

    Returns:
        RetrievedChunk with text, data and score.
    """
    payload = point.payload or {}
    return RetrievedChunk(
        chunk_id=str(point.id),
        text=payload.get("text", ""),
        retrieval_score=point.score or 0.0,
        file_id=payload.get("file_id", ""),
        filename=payload.get("filename", ""),
        page_start=payload.get("page_start"),
        page_end=payload.get("page_end"),
        section_title=payload.get("section_title"),
        chunk_index=payload.get("chunk_index", 0),
    )

def build_rbac_filter(
    workspace_id: str,
    allowed_role_ids: List[str],
    file_id: Optional[str] = None,
) -> qmodels.Filter:
    """RBAC filter per the architecture doc's key rule: enforced at the
    Qdrant query itself, never post-hoc. Primary filter is workspace_id +
    allowed_role_ids (most-permissive-wins is resolved upstream, at auth
    time, into this role list) -- NOT a precomputed file_id list. An
    optional file_id narrows to one file when the query rewrite step
    surfaces that scope (e.g. "what does the pricing doc say about X").
    """
    must: List[qmodels.Condition] = [
        qmodels.FieldCondition(
            key="workspace_id",
            match=qmodels.MatchValue(value=workspace_id),
        ),
        qmodels.FieldCondition(
            key="allowed_role_ids",
            match=qmodels.MatchAny(any=allowed_role_ids),
        ),
    ]
    if file_id:
        must.append(
            qmodels.FieldCondition(
                key="file_id",
                match=qmodels.MatchValue(value=file_id),
            )
        )
    return qmodels.Filter(must=must)


def hybrid_search(
    query: str,
    workspace_id: str,
    allowed_role_ids: List[str],
    file_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    client: Optional[QdrantClient] = None,
) -> list[RetrievedChunk]: 
    """Dense + sparse retrieval with RRF fusion, RBAC-filtered at the
    Qdrant query itself.

    Args:
        query: the rewritten query (post contextual query-rewrite step).
        workspace_id, allowed_role_ids: resolved at auth/RBAC time.
        file_id: optional query-scoped narrowing, from the rewrite step.
        limit: final result count after fusion.
        client: optional pre-built QdrantClient (mainly for testing).

    Returns:
        Qdrant's query_points response (points with payload + score).
    """
    client = client or _get_client()
    rbac_filter = build_rbac_filter(workspace_id, allowed_role_ids, file_id)

    prefetch = [
        qmodels.Prefetch(
            query=Document(
                text=query,
                model=DENSE_MODEL,
                options={
                    "jina-api-key": JINA_API_KEY,
                    "dimensions": DENSE_DIM,
                },
            ),
            using="dense",
            filter=rbac_filter,
            limit=PREFETCH_LIMIT,
        ),
        qmodels.Prefetch(
            query=Document(
                text=query,
                model=SPARSE_MODEL,
            ),
            using="sparse",
            filter=rbac_filter,
            limit=PREFETCH_LIMIT,
        ),
    ]

    logfire.info(
        "hybrid.py: running hybrid search",
        workspace_id=workspace_id,
        file_id=file_id,
        limit=limit,
    )

    results = _query_points(client, prefetch, limit)

    

    logfire.info(
        "hybrid.py: hybrid search complete",
        workspace_id=workspace_id,
        results=results.points,
        n_results=len(results.points),
    )

    retrieved_chunks = [
    _to_retrieved_chunk(point)
    for point in results.points
    ]

    retrieved_reranked_chunks = rerank_chunks(query, retrieved_chunks)

    logfire.info(
        "hybrid.py: reranking complete",
        workspace_id=workspace_id,
        n_results=len(retrieved_reranked_chunks),
        first_res=(
            retrieved_reranked_chunks[0]
            if retrieved_reranked_chunks
            else None
        ),
    )

    return retrieved_reranked_chunks
