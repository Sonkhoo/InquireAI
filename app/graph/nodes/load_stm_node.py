from app.graph.runtime import AgentState
from app.memory.memory import get_conversation


def load_stm_node(state: AgentState) -> dict:
    """
    Load the session history from memory and update the AgentState with it.
    """
    if "thread_id" not in state or "workspace_id" not in state:
        raise ValueError("thread_id and workspace_id must be provided in the state.")

    thread_id = state["thread_id"]
    workspace_id = state["workspace_id"]

    # Load the conversation history from memory
    history = get_conversation(
        user_id="00000000-0000-0000-0000-000000000001",  # Demo user ID
        workspace_id=workspace_id,
        thread_id=thread_id,
        limit=None,  # Load all messages
    )

    # Convert the history to a list of dicts with role and content
    session_history = [{"role": m["role"], "content": m["content"]} for m in history]

    # Update the state with the loaded session history
    state["session_history"] = session_history

    return {"session_history": session_history} 

