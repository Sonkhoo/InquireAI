"""
Shared graph state for the AI Core LangGraph pipeline.
"""

from typing import TypedDict
from typing_extensions import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from dataclasses import dataclass
from app.models import Citation, RetrievedChunk

@dataclass
class RequestContext:
    user_id: str
    workspace_id: str
    thread_id: str
    allowed_role_ids: list[str]


class AgentState(TypedDict, total=False):
    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]
    session_history: list[dict]  
    

    # Current query
    query: str
    rewritten_query: str # query after STM initally 
    retrieval_query: str #query after one hop
    file_id: str | None

    # Routing — matches ChatResponse.source naming (models.py) exactly
    route: Literal["doc_search", "general_chat"]

    # Retrieval
    retrieved_chunks: list[RetrievedChunk]
    reranked_chunks: list[RetrievedChunk]
    # Multi-hop evidence
    evidence_chunks: list[RetrievedChunk]


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
    hop_count: int

    # Agent reasoning
    retrieval_sufficient: bool
    missing_information: str | None