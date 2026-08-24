"""
LangGraph node: grounded synthesis + programmatic citation validation
(Architecture §1, query loop steps 16-17).
"""

from typing import cast

from app.graph.runtime import AgentState
from app.models import Citation, RetrievedChunk
from app.retrieval.synthesizer import synthesize_response
from app.logging import logfire


def synthesize_node(state: AgentState) -> dict:
    query = cast(str, state.get("query", ""))
    reranked_chunks = cast(list[RetrievedChunk], state.get("reranked_chunks", []))

    result = synthesize_response(query=query, retrieved_chunks=reranked_chunks)

    # Programmatic citation validation: only chunk_ids that actually
    # exist in the retrieved set survive — cheap lookup, catches hallucinated IDs.
    chunk_by_id = {chunk.chunk_id: chunk for chunk in reranked_chunks}
    citations: list[Citation] = []
    dropped: list[str] = []

    for chunk_id in result.citations:
        chunk = chunk_by_id.get(chunk_id)
        if chunk is None:
            dropped.append(chunk_id)
            continue
        citations.append(
            Citation(
                chunk_id=chunk.chunk_id,
                file_id=chunk.file_id,
                filename=chunk.filename,
                section_title=chunk.section_title,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
            )
        )

    if dropped:
        logfire.warning(
            "synthesize_node: dropped hallucinated chunk_ids",
            query=query,
            dropped=dropped,
        )

    return {"answer": result.response, "citations": citations}