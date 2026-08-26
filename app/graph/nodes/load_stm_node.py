from langgraph.runtime import Runtime
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
)

from app.graph.runtime import AgentState, RequestContext
from app.logging import logfire

def load_stm_node(
    state: AgentState,
    runtime: Runtime[RequestContext],
) -> dict:
    """
    Build STM context from LangGraph's checkpointed messages.

    Excludes the current user message because it is separately
    available as state["query"].
    """

    messages = state.get("messages", [])

    history_messages = messages

    if messages and isinstance(messages[-1], HumanMessage):
        history_messages = messages[:-1]

    session_history = []

    for message in history_messages:

        if isinstance(message, HumanMessage):
            role = "user"

        elif isinstance(message, AIMessage):
            role = "assistant"

        else:
            continue

        session_history.append(
            {
                "role": role,
                "content": str(message.content),
            }
        )

    logfire.info(
        "STM context loaded",
        session_history=session_history,
    )

    return {
        "session_history": session_history,
        "hop_count": 0,
    }