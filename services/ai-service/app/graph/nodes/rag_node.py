"""
LangGraph node: hybrid retrieval (dense + sparse, RRF-fused).
Reranking happens separately in rerank_node.
"""

from typing import cast

from app.graph.state import AgentState
from app.retrieval.hybrid import hybrid_search


def hybrid_search_node(state: AgentState) -> dict:
    query = cast(str, state.get("query", ""))
    workspace_id = cast(str, state.get("workspace_id", ""))
    file_id = cast("str | None", state.get("file_id"))
    allowed_role_ids = cast(list[str], state.get("allowed_role_ids", []))
    limit = 10  # TODO: move to settings once tuned empirically (Architecture §14 item 2)

    retrieved_chunks = hybrid_search(
        query=query,
        allowed_role_ids=allowed_role_ids,
        workspace_id=workspace_id,
        file_id=file_id,
        limit=limit,
    )

    return {"retrieved_chunks": retrieved_chunks}