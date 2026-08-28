from typing import cast, Any, List
from app.graph.runtime import AgentState, RequestContext
from app.models import RetrievedChunk, Citation, ChunkMetadata
from app.retrieval.hybrid import hybrid_search
from app.retrieval.confidence import compute_confidence
from langgraph.runtime import Runtime


def hybrid_search_node(state, runtime: Runtime[RequestContext]) -> dict[str, List[RetrievedChunk]]:
    query = state["retrieval_query"]

    chunks = hybrid_search(
        query=query,
        allowed_role_ids=runtime.context.allowed_role_ids,
        workspace_id=runtime.context.workspace_id,
    )

    return {
        "retrieved_chunks": chunks
    }