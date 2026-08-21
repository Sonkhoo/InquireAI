"""
LangGraph node: composite confidence scoring + abstention decision.
"""

from typing import cast

from app.graph.state import AgentState
from app.models import RetrievedChunk
from app.retrieval.confidence import compute_confidence
from app.logging import logfire


CONFIDENCE_THRESHOLD = 0.5


def confidence_node(state: AgentState) -> dict:
    query = cast(str, state.get("query", ""))
    reranked_chunks = cast(list[RetrievedChunk], state.get("reranked_chunks", []))
    confidence = compute_confidence(query=query, retrieved_chunks=reranked_chunks)
    abstained = confidence < CONFIDENCE_THRESHOLD

    if abstained:
        logfire.info(
            "confidence_node: below threshold, will abstain",
            query=query,
            confidence=confidence,
            threshold=CONFIDENCE_THRESHOLD,
        )

    return {"confidence": confidence, "abstained": abstained}