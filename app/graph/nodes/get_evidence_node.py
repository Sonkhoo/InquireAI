"""
LangGraph node: accumulate evidence across multi-hop retrievals.

The node takes the latest reranked chunks and merges them into the
persistent evidence set used by the sufficiency evaluator and
final synthesizer.
"""

from app.graph.runtime import AgentState
from app.models import RetrievedChunk
from app.logging import logfire


def accumulate_evidence_node(state: AgentState) -> dict:
    """
    Accumulate reranked evidence across retrieval hops.

    Each hop produces:
        retrieved_chunks
            ↓
        reranked_chunks

    This node merges the new reranked chunks into:
        evidence_chunks

    Duplicate chunks are removed using chunk_id.
    """

    existing_evidence = state.get(
        "evidence_chunks",
        [],
    )

    current_chunks = state.get(
        "reranked_chunks",
        [],
    )

    # Build a set of IDs already present in accumulated evidence.
    existing_ids = {
        chunk.chunk_id
        for chunk in existing_evidence
    }

    new_chunks: list[RetrievedChunk] = []

    for chunk in current_chunks:

        if chunk.chunk_id not in existing_ids:
            new_chunks.append(chunk)
            existing_ids.add(chunk.chunk_id)

    accumulated_evidence = [
        *existing_evidence,
        *new_chunks,
    ]

    logfire.info(
        "Evidence accumulated",
        previous_count=len(existing_evidence),
        new_count=len(new_chunks),
        total_count=len(accumulated_evidence),
        hop_count=state.get("hop_count", 0),
    )

    return {
        "evidence_chunks": accumulated_evidence,
    }