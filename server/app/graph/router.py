"""
Assembles the AI Core LangGraph pipeline.
"""

from langgraph.graph import END, START, StateGraph
from psycopg import Connection
from psycopg.rows import DictRow, dict_row  
from psycopg_pool import ConnectionPool  
from langgraph.checkpoint.postgres import PostgresSaver  


from app.config import get_settings
from app.graph.nodes.load_stm_node import load_stm_node
from app.graph.nodes.abstain_node import abstain_node
from app.graph.nodes.confidence_node import confidence_node
from app.graph.nodes.retrieval_node import retrieval_planner_node
from app.graph.nodes.suffieciency_node import sufficiency_node
from app.graph.nodes.get_evidence_node import accumulate_evidence_node
from app.graph.nodes.rag_node import hybrid_search_node
from app.graph.nodes.rerank_node import rerank_node
from app.graph.nodes.stm_rewrite_node import stm_rewrite_node
from app.graph.nodes.general_chat_node import general_chat_node
from app.graph.nodes.router_node import intent_router_node
from app.graph.nodes.synthesize_node import synthesize_node
from app.graph.nodes.increment_hop import increment_hop_node
from app.graph.runtime import AgentState, RequestContext
from app.graph.nodes.guard_node import guard_node
settings = get_settings()

from app.logging import logfire

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

def _route_on_hop_count(state: AgentState) -> str:
    hop_count = state.get("hop_count", 0)
    if hop_count >= settings.MAX_HOPS:
        return "abstain"
    else:
        return "synthesize"

    
def _route_on_confidence(state: AgentState) -> str:
    confidence = state.get("confidence", 0.0)
    if confidence >= settings.CONFIDENCE_THRESHOLD:
        return "synthesize"
    else:
        hop_count = state.get("hop_count", 0)
        if hop_count >= settings.MAX_HOPS:
            return "abstain"
        else:
            return "synthesize"  
def _route_after_guard(state: AgentState) -> str:
    guard_status = state.get("guard_status")
    logfire.info("Guard condition for route:", guard_status=guard_status)

    if guard_status == "allowed":
        return "allowed"
    else:
        return "blocked"
    
def _route_after_sufficiency(state: AgentState) -> str:

    # Enough evidence to generate a grounded answer.
    if state.get("retrieval_sufficient", False):
        return "synthesize"

    # Evidence is insufficient, but retrieval budget remains.
    if state.get("hop_count", 0) < settings.MAX_HOPS:
        return "retrieval_planner"

    # Retrieval budget exhausted.
    return "abstain"


def _route_after_intent(state: AgentState) -> str:
    route = state.get("route")
    if route not in ["doc_search", "general_chat", "off_topic"]:
        raise ValueError(f"Invalid route: {route}")
    return route

def build_graph():
    graph = StateGraph(AgentState, context_schema=RequestContext)
    graph.add_node("guard", guard_node) # check for prompt injection and PII in the user query
    graph.add_node("load_stm", load_stm_node) # load session history from DB using RequestContext
    graph.add_node("rewrite_query", stm_rewrite_node) # rewrite the user query using STM and session history
    graph.add_node("intent_router", intent_router_node) # route the user's query to the appropriate node
    graph.add_node("general_chat", general_chat_node) # test node for debugging
    graph.add_node("retrieval_planner", retrieval_planner_node) # plan the next retrieval query based on the current evidence and missing information
    graph.add_node("hybrid_search", hybrid_search_node) # perform a hybrid search using Qdrant with RRF fusion of sparse and dense retrieval results
    graph.add_node("rerank", rerank_node) # rerank the retrieved chunks based on the query using a cross-encoder model
    graph.add_node("confidence", confidence_node) # formulate a score based on evidence agreement and top evidence
    graph.add_node("accumulate_evidence",accumulate_evidence_node) # accumulate evidence from the retrieved chunks and the user query
    graph.add_node("sufficiency",sufficiency_node) # checks if the accumulated evidence is sufficient to answer the query, and if not, what information is missing
    graph.add_node("increment_hop", increment_hop_node) # increment the hop count for multi-hop retrieval
    graph.add_node("synthesize", synthesize_node) # generate a response based on the retrieved chunks and the user query with citations
    graph.add_node("abstain", abstain_node)

    graph.add_edge(START, "guard")
    graph.add_conditional_edges(
        "guard",
        _route_after_guard,
        {
            "allowed": "load_stm",
            "blocked": "abstain",
        },
    )
    graph.add_edge("load_stm", "rewrite_query")
    graph.add_edge("rewrite_query", "intent_router")
    graph.add_conditional_edges(
        "intent_router",
        _route_after_intent,
        {
            "general_chat": "general_chat",
            "doc_search": "retrieval_planner",
            "off_topic": "abstain",
        },
    )
    graph.add_edge("general_chat", END)
    graph.add_edge("retrieval_planner", "increment_hop")
    graph.add_edge("increment_hop", "hybrid_search")
    graph.add_edge("hybrid_search", "rerank")
    graph.add_edge("rerank", "confidence")
    graph.add_edge("confidence", "accumulate_evidence")
    graph.add_edge("accumulate_evidence", "sufficiency")
    graph.add_conditional_edges(
        "sufficiency",
        _route_after_sufficiency,
        {
            "synthesize": "synthesize",
            "retrieval_planner": "retrieval_planner",
            "abstain": "abstain",
        },
    )
    graph.add_edge("synthesize", END)
    graph.add_edge("abstain", END)

    return graph.compile(checkpointer=get_checkpointer())


agent_graph = build_graph()