import time
import uuid as uuidlib
from fastapi import APIRouter, HTTPException
from app.config import get_settings
from app.memory import memory
from app.graph.router import agent_graph
from app.graph.runtime import AgentState
from app.logging import logfire
from app.models import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])
settings = get_settings()


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    start = time.perf_counter()
    logfire.debug(
        "chat: start",
        thread_id=request.thread_id,
        workspace_id=request.workspace_id,
        message_length=len(request.message),
        allowed_role_ids=request.allowed_role_ids,
    )
    try:
        # 0. Resolve the demo user from the DB (auth is skipped for the demo).
        user = memory.get_user_by_email(request.user_email)
        if not user:
            raise HTTPException(status_code=404, detail=f"Unknown demo user: {request.user_email}")
        user_id = str(user["id"])
        logfire.debug("chat: user resolved", user_id=user_id, role=user["role"])
        user = memory.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
        
        if not user["workspace_id"] or user["workspace_id"] != request.workspace_id:
            raise HTTPException(status_code=404, detail=f"User {user_id} has no associated workspace")




        # 1. Ensure the conversation exists (idempotent)
        memory.create_conversation(
            id=request.thread_id,
            user_id=user_id,
            workspace_id=request.workspace_id,
            title="New conversation",
        )
        logfire.debug("chat: conversation ensured", thread_id=request.thread_id)

        # 2. Load history from DB instead of trusting the client
        history = memory.get_conversation(
            user_id=user_id,
            workspace_id=request.workspace_id,
            thread_id=request.thread_id,
        )
        session_history = [
            {"role": m["role"], "content": m["content"]} for m in history
        ]
        logfire.debug(
            "chat: history loaded",
            thread_id=request.thread_id,
            history_len=len(session_history),
            last_message=session_history[-1] if session_history else None,
        )

        # 3. Persist the user's turn BEFORE running the graph
        memory.add_message(request.thread_id, "user", request.message)
        logfire.debug("chat: user message persisted", thread_id=request.thread_id, message_preview=request.message[:200])

        # 4. Run the graph with server-side history
        input_state: AgentState = {
            "query": request.message,
            "workspace_id": request.workspace_id,
            "allowed_role_ids": request.allowed_role_ids,
            "thread_id": request.thread_id,
            "session_history": session_history,
            "route": "doc_search",
        }
        logfire.debug("chat: invoking graph", input_state=input_state)

        result = agent_graph.invoke(
            input_state,
            config={"configurable": {"thread_id": request.thread_id}}
        )

        graph_keys = list(result.keys())
        logfire.debug(
            "chat: graph finished",
            graph_keys=graph_keys,
            route=result.get("route"),
            confidence=result.get("confidence"),
            abstained=result.get("abstained", False),
            num_citations=len(result.get("citations", [])),
            answer_preview=(result.get("answer") or "")[:200],
        )

        # 5. Persist the assistant's turn + metadata
        answer = result.get("answer", "")
        meta = {
            "citations": [
                citation.model_dump(mode="json")
                for citation in result.get("citations", [])
            ],
            "confidence": result.get("confidence"),
            "abstained": result.get("abstained", False),
            "model_used": settings.enrich_model,
        }
        memory.add_message(request.thread_id, "assistant", answer, meta)
        logfire.debug("chat: assistant message persisted", thread_id=request.thread_id, answer_preview=answer[:200], metadata=meta)

        elapsed = time.perf_counter() - start
        logfire.debug("chat: done", thread_id=request.thread_id, processing_time=elapsed)

        return ChatResponse(
            thread_id=request.thread_id,
            response=answer,
            source=result.get("route", "doc_search"),
            citations=result.get("citations", []),
            confidence=result.get("confidence"),
            abstained=result.get("abstained", False),
            model_used=settings.enrich_model,
            processing_time=elapsed,
        )
    except Exception as e:
        logfire.exception("chat: error during chat", thread_id=request.thread_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))