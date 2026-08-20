"""
Chat routes for the InquireAI service.
"""

import time

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.graph.router import agent_graph
from app.graph.state import AgentState
from app.logging import logfire
from app.models import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])
settings = get_settings()


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint — runs the retrieval + synthesis graph for a query.
    """
    start = time.perf_counter()
    try:
        logfire.info(
            "chat.py: chat request received",
            query=request.message,
            workspace_id=request.workspace_id,
        )

        input_state: AgentState = {
            "query": request.message,
            "workspace_id": request.workspace_id,
            "allowed_role_ids": request.allowed_role_ids,
            "thread_id": request.thread_id,
            "route": "doc_search",  # hardcoded until the planner/router node exists
        }

        result = agent_graph.invoke(input_state)
        processing_time = time.perf_counter() - start

        logfire.info(
            "chat.py: graph invocation complete",
            query=request.message,
            n_retrieved=len(result.get("retrieved_chunks", [])),
            n_reranked=len(result.get("reranked_chunks", [])),
            confidence=result.get("confidence"),
            abstained=result.get("abstained", False),
        )

        return ChatResponse(
            thread_id=request.thread_id,
            response=result.get("answer", ""),
            source=result.get("route", "doc_search"),
            citations=result.get("citations", []),
            confidence=result.get("confidence"),
            abstained=result.get("abstained", False),
            model_used=settings.enrich_model,
            processing_time=processing_time,
        )

    except Exception as e:
        logfire.error("chat.py: error during chat", error=str(e), query=request.message)
        raise HTTPException(status_code=500, detail=str(e))