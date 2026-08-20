"""
Assembles the AI Core LangGraph pipeline.

Current flow (Layer 0 — no router/planner/persistence/web-search yet):
    START -> hybrid_search -> rerank -> confidence -> (synthesize | abstain) -> END
"""

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.abstain_node import abstain_node
from app.graph.nodes.confidence_node import confidence_node
from app.graph.nodes.rag_node import hybrid_search_node
from app.graph.nodes.rerank_node import rerank_node
from app.graph.nodes.synthesize_node import synthesize_node
from app.graph.state import AgentState


def _route_on_confidence(state: AgentState) -> str:
    return "abstain" if state.get("abstained", False) else "synthesize"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("hybrid_search", hybrid_search_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("confidence", confidence_node)
    graph.add_node("synthesize", synthesize_node)
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

    return graph.compile()


agent_graph = build_graph()