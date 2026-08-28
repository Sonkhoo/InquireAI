"""
LangGraph node: cross-encoder reranking of hybrid-retrieved chunks.
"""

from typing import cast

from app.graph.runtime import AgentState
from app.models import RetrievedChunk
from app.retrieval.reranker import rerank_chunks


def rerank_node(state: AgentState) -> dict:
    query = cast(str, state.get("query", ""))
    retrieved_chunks = cast(list[RetrievedChunk], state.get("retrieved_chunks", []))

    if not retrieved_chunks:
        return {"reranked_chunks": []}

    reranked_chunks = rerank_chunks(query=query, retrieved_chunks=retrieved_chunks)
    return {"reranked_chunks": reranked_chunks}