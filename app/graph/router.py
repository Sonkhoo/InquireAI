"""
Assembles the AI Core LangGraph pipeline.
"""

from langgraph.graph import END, START, StateGraph
from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

from app.config import get_settings
from app.graph.nodes.abstain_node import abstain_node
from app.graph.nodes.confidence_node import confidence_node
from app.graph.nodes.rag_node import hybrid_search_node
from app.graph.nodes.rerank_node import rerank_node
from app.graph.nodes.synthesize_node import synthesize_node
from app.graph.runtime import AgentState

settings = get_settings()

_checkpointer: PostgresSaver | None = None

# The checkpointer is a global singleton that is lazily initialized on first use.
def get_checkpointer() -> PostgresSaver:
    global _checkpointer
    if _checkpointer is None:
        pool: ConnectionPool[Connection[DictRow]] = ConnectionPool(
            conninfo=settings.db_url,
            max_size=settings.DB_POOL_SIZE,
            open=True,
            kwargs={"autocommit": True,"row_factory": dict_row},
        )
        _checkpointer = PostgresSaver(pool)
        _checkpointer.setup()
    return _checkpointer


def _route_on_confidence(state: AgentState) -> str:
    return "abstain" if state.get("abstained", False) else "synthesize"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("hybrid_search", hybrid_search_node) # perform a hybrid search using Qdrant with RRF fusion of sparse and dense retrieval results
    graph.add_node("rerank", rerank_node) # rerank the retrieved chunks based on the query using a cross-encoder model
    graph.add_node("confidence", confidence_node) # formulate a score based on evidence agreement and top evidence
    graph.add_node("synthesize", synthesize_node) # generate a response based on the retrieved chunks and the user query with citations
    graph.add_node("abstain", abstain_node)

    graph.add_edge(START, "hybrid_search")
    graph.add_edge("hybrid_search", "rerank")
    graph.add_edge("rerank", "confidence")
    graph.add_conditional_edges(
        "confidence",
        _route_on_confidence,
        {"synthesize": "synthesize", "abstain": "abstain"},
    )
    graph.add_edge("synthesize", END)
    graph.add_edge("abstain", END)

    return graph.compile(checkpointer=get_checkpointer())


agent_graph = build_graph()