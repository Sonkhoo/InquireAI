import uuid as uuidlib
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.memory import memory

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"

class CreateConversationRequest(BaseModel):
    workspace_id: str
    title: str = "New conversation"

class RenameRequest(BaseModel):
    title: str


@router.post("")
def create_conversation(payload: CreateConversationRequest):
    thread_id = str(uuidlib.uuid4())
    memory.create_conversation(thread_id, DEMO_USER_ID, payload.workspace_id, payload.title)
    return {"thread_id": thread_id, "title": payload.title}


@router.get("")
def list_conversations(workspace_id: str):
    return memory.get_all_conversations(DEMO_USER_ID, workspace_id)


@router.get("/{thread_id}/messages")
def get_messages(thread_id: str, workspace_id: str):
    msgs = memory.get_conversation(DEMO_USER_ID, workspace_id, thread_id, limit=None)
    if not msgs:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return msgs


@router.patch("/{thread_id}")
def rename_conversation(thread_id: str, payload: RenameRequest):
    memory.rename_conversation(thread_id, DEMO_USER_ID, payload.title)
    return {"ok": True}


@router.delete("/{thread_id}")
def delete_conversation(thread_id: str):
    memory.delete_conversation(thread_id, DEMO_USER_ID)
    return {"ok": True}