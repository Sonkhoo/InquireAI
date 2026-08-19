"""
Shared graph state for the AI Core LangGraph pipeline.
"""

from typing import TypedDict
from typing_extensions import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

from app.models import Citation, RetrievedChunk


class AgentState(TypedDict, total=False):
    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]
    thread_id: str

    # Request identity (auth skipped for demo — workspace/roles sent by client)
    workspace_id: str
    allowed_role_ids: list[str]

    # Current query
    query: str
    rewritten_query: str
    file_id: str | None

    # Routing — matches ChatResponse.source naming (models.py) exactly
    route: Literal["doc_search", "web_search", "general_chat"]

    # Retrieval
    retrieved_chunks: list[RetrievedChunk]
    reranked_chunks: list[RetrievedChunk]

    # Generation
    answer: str
    citations: list[Citation]

    # Evaluation
    confidence: float
    grounded: bool
    citation_coverage: float
    unsupported_claims: list[str]
    abstained: bool

    # Control
    retry_count: int
    correction_strategy: str