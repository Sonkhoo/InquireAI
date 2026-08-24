from typing import cast, Any, List
from app.graph.runtime import AgentState
from app.models import RetrievedChunk, Citation, ChunkMetadata
from app.retrieval.hybrid import hybrid_search
from app.retrieval.confidence import compute_confidence
from langchain_core.tools import tool



@tool
def search_tool(query: str, allowed_role_ids: List[str], file_id: str | None, workspace_id: str) -> List[RetrievedChunk]:
    """
    Perform a hybrid search using Qdrant with RRF fusion of sparse and dense retrieval results.
    """

    # Perform hybrid search
    retrieved_chunks = hybrid_search(query, allowed_role_ids=allowed_role_ids, file_id=file_id, workspace_id=workspace_id)

    # Compute confidence score based on evidence agreement and top evidence
    confidence_score = compute_confidence(query, retrieved_chunks)

    return retrieved_chunks