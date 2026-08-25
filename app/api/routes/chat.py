import time
import uuid as uuidlib
from fastapi import APIRouter, HTTPException
from app.config import get_settings
from app.memory import memory
from app.graph.router import agent_graph
from app.graph.runtime import AgentState
from app.logging import logfire
from app.models import ChatRequest, ChatResponse
from app.graph.runtime import RequestContext
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage

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
    )
    try:

        user_email = request.user_email
        print(f"chat: user_email={user_email}, workspace_id={request.workspace_id}, thread_id={request.thread_id}")
        logfire.info(
            "chat: request received",
            user_email=user_email,
            workspace_id=request.workspace_id,
            thread_id=request.thread_id,
            message_length=len(request.message),
        )
        user_workspace_id = request.workspace_id
        user_thread_id = request.thread_id

        # 0. Resolve the demo user from the DB (auth is skipped for the demo).
        user = memory.get_user_by_email(user_email)
        if not user:
            raise HTTPException(status_code=404, detail=f"Unknown demo user: {user_email}")
        user_id = str(user["id"])
        logfire.debug("chat: user resolved", user_id=user_id, role=user["role"])


        user = memory.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
        
        db_workspace_id = user.get("workspace_id")
        requested_workspace_id = uuidlib.UUID(str(request.workspace_id))
        if not db_workspace_id:
            raise HTTPException(
                status_code=404,
                detail=f"User {user_id} has no associated workspace"
            )

        if db_workspace_id != requested_workspace_id:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"User {user_id} does not belong to workspace "
                    f"{requested_workspace_id} "
                    f"(db={db_workspace_id})"
                )
            )
        #user_workspace_id = requested_workspace_id
        if user_thread_id is None or not user_thread_id.strip():
            user_thread_id = str(uuidlib.uuid4())
            memory.create_conversation(
                id=user_thread_id,
                user_id=user_id,
                workspace_id=user_workspace_id,
                title="New conversation",
            )
            logfire.debug("chat: conversation created", thread_id=user_thread_id)
        elif not memory.conversation_belongs_to_user(
            thread_id=user_thread_id,
            user_id=user_id,
            workspace_id=user_workspace_id,
        ):
            raise HTTPException(status_code=404, detail="Conversation not found")


        # 3. Persist the user's turn BEFORE running the graph
        memory.add_message(user_thread_id, "user", request.message)
        logfire.debug("chat: user message persisted", thread_id=user_thread_id, message_preview=request.message[:200])

        # 4. Run the graph with server-side history
        input_state: AgentState = {
            "query": request.message,
            "messages": [
                HumanMessage(content=request.message)
            ],
        }
        logfire.debug("chat: invoking graph", input_state=input_state)

        result = agent_graph.invoke(
            input_state,
            config={"configurable": {"thread_id": user_thread_id}},
            context=RequestContext(
                user_id=user_id,
                workspace_id=user_workspace_id,
                thread_id=user_thread_id,
                allowed_role_ids=request.allowed_role_ids,
            ),
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
            "model_used": result.get("model_used"),
        }
        memory.add_message(user_thread_id, "assistant", answer, meta)
        logfire.debug("chat: assistant message persisted", thread_id=user_thread_id, answer_preview=answer[:200], metadata=meta)

        elapsed = time.perf_counter() - start
        logfire.debug("chat: done", thread_id=user_thread_id, processing_time=elapsed)

        return ChatResponse(
            thread_id=user_thread_id,
            response=answer,
            source=result.get("route", "doc_search"),
            citations=result.get("citations", []),
            confidence=result.get("confidence"),
            abstained=result.get("abstained", False),
            model_used=str(result.get("model_used")),
            processing_time=elapsed,
        )
    except HTTPException:
        raise
    except Exception as e:
        logfire.exception("chat: error during chat", thread_id=user_thread_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))