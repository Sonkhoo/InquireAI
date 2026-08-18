

from langchain_core.messages import AnyMessage
from langchain_protocol import TypedDict
from langgraph.graph import add_messages
from typing_extensions import Annotated, Literal
from models import RetrievedChunk, Citation

class AgentState(TypedDict, total=False):

    # Conversation
    messages: Annotated[list[AnyMessage], add_messages]
    thread_id: str

    # Request identity
    user_id: str
    workspace_id: str
    allowed_role_ids: list[str]

    # Current query
    query: str
    rewritten_query: str
    file_id: str | None

    # Routing
    route: Literal[
        "document_rag",
        "github_tool",
        "general_chat",
    ]

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