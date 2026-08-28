"""
LangGraph node: composite confidence scoring + abstention decision.
Based on the chunk agreement and top chunk confidence
"""

from typing import cast

from app.graph.runtime import AgentState
from app.models import RetrievedChunk
from app.retrieval.confidence import compute_confidence
from app.logging import logfire



def confidence_node(state: AgentState) -> dict:

    query = cast(
        str,
        state.get("retrieval_query", "")
    )

    reranked_chunks = cast(
        list[RetrievedChunk],
        state.get("reranked_chunks", [])
    )

    confidence = compute_confidence(
        query=query,
        retrieved_chunks=reranked_chunks,
    )

    return {
        "confidence": confidence,
    }