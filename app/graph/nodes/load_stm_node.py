from email import message
from langgraph.runtime import Runtime
from app.graph.runtime import AgentState, RequestContext
from app.memory.memory import get_conversation
from app.logging import logfire
def load_stm_node(state: AgentState, runtime: Runtime[RequestContext]) -> dict:
    """
    Load the session history from memory and update the AgentState with it.

    Identity (user_id / workspace_id / thread_id) comes from the immutable
    RequestContext, not from mutable graph state.
    """
    context = runtime.context

    # Load the conversation history from memory
    history = get_conversation(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
        thread_id=context.thread_id,
        limit=None,  # Load all messages
    )
    logfire.info("history", history=history)

    return {"session_history":[
        {"role": message["role"], "content": message["content"]} for message in history
    ] } 

