"""
LangGraph node: hybrid retrieval (dense + sparse, RRF-fused).
Reranking happens separately in rerank_node.
"""

from typing import cast
from langgraph.runtime import Runtime
from app.graph.runtime import AgentState, RequestContext
from app.retrieval.hybrid import hybrid_search


def hybrid_search_node(state: AgentState, runtime: Runtime[RequestContext]) -> dict:
    query = cast(str, state.get("query", ""))
    file_id = cast("str | None", state.get("file_id"))
    "invoked from context which has RequestContext, so we can access user_id, workspace_id, thread_id, allowed_role_ids"
    context = runtime.context
    workspace_id = context.workspace_id
    allowed_role_ids = context.allowed_role_ids
    limit = 10  # TODO: move to settings once tuned empirically (Architecture §14 item 2)

    retrieved_chunks = hybrid_search(
        query=query,
        allowed_role_ids=allowed_role_ids,
        workspace_id=workspace_id,
        file_id=file_id,
        limit=limit,
    )

    return {"retrieved_chunks": retrieved_chunks}