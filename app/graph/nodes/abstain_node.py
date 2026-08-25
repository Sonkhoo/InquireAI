"""
LangGraph node: graceful non-answer. Never confirms or denies that a
matching (possibly restricted) document exists — Architecture §1 key rule.
"""

from app.graph.runtime import AgentState

ABSTAIN_MESSAGE = "BITCH, I DON'T KNOW. I CANNOT ANSWER THAT QUESTION."  # noqa: E501


def abstain_node(state: AgentState) -> dict:
    return {"answer": ABSTAIN_MESSAGE, "citations": []}