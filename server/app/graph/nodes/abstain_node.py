"""
LangGraph node: graceful non-answer. Never confirms or denies that a
matching (possibly restricted) document exists — Architecture §1 key rule.
"""

from app.graph.runtime import AgentState

ABSTAIN_MESSAGE = "I'm sorry, but I cannot answer that question based on the information available to me."  


def abstain_node(state: AgentState) -> dict:
    return {"answer": ABSTAIN_MESSAGE, "citations": []}