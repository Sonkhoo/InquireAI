"""
Increment hop count in the state graph. This node is used to track the number of hops taken in a multi-hop retrieval process. It increments the hop count by 1 each time it is called, and checks if the maximum number of hops has been reached. If the maximum number of hops is reached, it raises an exception to prevent further processing.
"""
from typing import cast
from app.graph.runtime import AgentState
from app.config import get_settings

settings = get_settings()
MAX_HOPS = settings.MAX_HOPS


def increment_hop_node(state: AgentState) -> dict:
    hop_count = cast(int, state.get("hop_count", 0))


    return {"hop_count": hop_count + 1}