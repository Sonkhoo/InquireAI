"""
query/retrieval/hybrid.py

Query-time hybrid retrieval: dense (Jina v4) + sparse (BM25) + RRF fusion,
with RBAC enforced as part of the same Qdrant query (not post-hoc).

Mirrors store.py exactly on the embedding side: same DENSE_MODEL,
SPARSE_MODEL, DENSE_DIM, and Qdrant Cloud Inference via Document(text=...,
model=...).

NOTE: no `task` option is set here (see store.py's matching note) -- Jina
v4 ideally wants "retrieval.query" on this side vs "retrieval.passage" at
index time, but I could not confirm Qdrant's Cloud Inference options
schema actually honors that key for this model. Check the Inference tab
in the Qdrant Cloud Console before adding it back on both sides.
"""

from __future__ import annotations

from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Document
from qdrant_client.http import models as qmodels

from app.logging import logfire
from app.config import get_settings
from app.ingestion.store import (
    _get_client,
    COLLECTION_NAME,
    DENSE_MODEL,
    SPARSE_MODEL,
    DENSE_DIM,
    JINA_API_KEY,
)

settings = get_settings()

PREFETCH_LIMIT = 20
DEFAULT_LIMIT = 10


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
):
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

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=prefetch,
        query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
        limit=limit,
        with_payload=True,
    )

    logfire.info(
        "hybrid.py: hybrid search complete",
        workspace_id=workspace_id,
        n_results=len(results.points),
    )

    return results.points