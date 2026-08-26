import uuid as uuidlib
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from streamlit import user
from app.memory import memory

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

class CreateConversationRequest(BaseModel):
    user_email: str
    workspace_id: str
    title: str = "New conversation"

class RenameRequest(BaseModel):
    title: str

def _get_user_id(user_email: str) -> str:
    """Retrieve the user ID for a given email."""
    user = memory.get_user_by_email(user_email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user["id"]

@router.post("")
def create_conversation(payload: CreateConversationRequest):
    thread_id = str(uuidlib.uuid4())
    user_id = _get_user_id(payload.user_email)
    memory.create_conversation(thread_id, user_id, payload.workspace_id, payload.title)
    return {"thread_id": thread_id, "title": payload.title}


@router.get("")
def list_conversations(workspace_id: str, user_email: str):
    user_id = _get_user_id(user_email)
    return memory.get_all_conversations(user_id, workspace_id)


@router.get("/{thread_id}/messages")
def get_messages(thread_id: str, workspace_id: str, user_email: str):
    user_id = _get_user_id(user_email)
    msgs = memory.get_conversation(user_id, workspace_id, thread_id, limit=None)
    if not msgs:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return msgs


@router.patch("/{thread_id}")
def rename_conversation(thread_id: str, user_email: str, payload: RenameRequest):
    user_id = _get_user_id(user_email)
    memory.rename_conversation(thread_id, user_id, payload.title)
    return {"ok": True}


@router.delete("/{thread_id}")
def delete_conversation(thread_id: str, user_email: str):
    user_id = _get_user_id(user_email)
    memory.delete_conversation(thread_id, user_id)
    return {"ok": True}