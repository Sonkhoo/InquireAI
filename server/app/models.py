"""
API request/response models and internal data contracts for the AI service.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field


# --- Chat contract ------------------------------------------------------------

class ChatRequest(BaseModel):
    """Model for incoming chat requests. Called by the Gateway, which has
    already resolved auth and accessible_file_ids before this point."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,  
        description="The user's raw query.",
    )
    user_email: str = Field(
        ...,
        description="Demo stand-in for auth: email of the seeded user sending this message.",
    )
    thread_id: str | None = Field(
        default=None,
        description="Existing conversation ID; omitted to start a new conversation.",
    )
    workspace_id: str = Field(
        ...,
        description="Workspace the request is scoped to.",
    )
    session_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Prior turns in this thread, for contextual query rewrite.",
    )


class ChatResponse(BaseModel):
    """Model for chat responses."""

    thread_id: str = Field(..., description="Echoes the request's thread_id.")
    response: str = Field(..., description="The synthesized answer text.")
    source: Literal["doc_search", "off_topic", "general_chat"] = Field(
        ..., description="Which router branch produced this answer."
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Structured chunk_id references backing the answer. Empty when abstained or general_chat.",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0, le=1.0,
        description="Composite retrieval + citation confidence score. None for general_chat.",
    )
    abstained: bool = Field(
        default=False,
        description="True when confidence fell below threshold — response is a graceful non-answer.",
    )
    model_used: str = Field(..., description="The LLM used to generate the response.")
    processing_time: float = Field(..., description="Time taken to process the request, in seconds.")
    token_usage: dict[str, Any] | None = Field(default=None)
    cached: bool = Field(default=False, description="True if served from the RBAC-safe response cache.")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Citation(BaseModel):
    chunk_id: str
    file_id: str
    filename: str | None = None
    section_title: str | None = None
    page_start: int | None = None
    page_end: int | None = None


# --- Upload contract ------------------------------------------------------------

class UploadResponse(BaseModel):
    """
    Response returned after a document is successfully uploaded
    and processed through the ingestion pipeline.
    """

    file_id: str = Field(
        ..., description="Unique identifier assigned to the uploaded file.",
    )

    filename: str = Field(
        ..., description="Original filename uploaded by the user.",
    )

    chunks_stored: int = Field(
        ...,
        ge=0, description="Number of chunks successfully stored in Qdrant.",
    )

    status: Literal["success"] = Field(
        default="success",
        description="Upload and ingestion status.",
    )

# --- Health / errors ------------------------------------------------------------

class HealthCheckResponse(BaseModel):
    status: str = Field(default="healthy")
    uptime: float = Field(..., description="Service uptime in seconds.")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = Field(default="1.0.0")
    environment: str = Field(default="development")
    checks: list[dict[str, Any]] | None = Field(
        default=None,
        description="Per-dependency checks, e.g. [{'service': 'qdrant', 'ok': true}]",
    )


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable error message.")


class ErrorResponse(BaseModel):
    """Matches the architecture doc's stated shape: { error: { code, message } }"""
    error: ErrorDetail


# --- Chunk / document contracts (ingestion + retrieval) ------------------------

class ChunkMetadata(BaseModel):
    file_id: str = Field(..., description="Source file's unique identifier.")
    workspace_id: str = Field(..., description="Workspace that owns the chunk.")
    filename: str = Field(..., description="Source filename.")
    allowed_role_ids: list[str] = Field(
        default_factory=list,
        description="Roles allowed to read this chunk — enforced as the Qdrant RBAC filter.",
    )
    chunk_index: int = Field(..., ge=0, description="Zero-based index within the document.")
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_title: str | None = Field(default=None)
    token_count: int = Field(..., ge=0)
    context_summary: str | None = Field(
        default=None,
        description="Groq-generated 1-2 sentence contextual summary, prepended before embedding (§1 step 9).",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Chunk(BaseModel):
    """Canonical chunk record — written to Qdrant, cited in ChatResponse.
    chunk_index/page_start/page_end live only on `metadata` to avoid dual
    sources of truth; do not duplicate them here."""

    id: str = Field(..., description="Unique chunk identifier — this is the chunk_id cited in answers.")
    text: str = Field(..., description="Contextualized, cleaned chunk text (pre-context_summary prepend).")
    embedding: list[float] | None = Field(default=None, description="Populated by embed.py; None until embedded.")
    metadata: ChunkMetadata = Field(...)

class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str

    retrieval_score: float
    rerank_score: float | None = None
    confidence: float | None = None
    file_id: str
    filename: str
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    chunk_index: int

class SynthesizedAnswer(BaseModel):
    response: str
    citations: list[str] = Field(default_factory=list)

class Document(BaseModel):
    """Mirrors the Postgres `files` row — tracking/status, not chunk content."""

    id: str = Field(..., description="Unique document identifier.")
    filename: str = Field(..., description="Original filename.")
    file_type: str = Field(..., description="pdf | docx | xlsx | md")
    workspace_id: str = Field(..., description="Workspace that owns the document.")
    storage_backend: Literal["s3", "disk"] = Field(..., description="Which StorageAdapter implementation holds this file.")
    storage_key: str = Field(..., description="Storage location key, meaningful only alongside storage_backend.")
    uploaded_at: datetime = Field(...)
    total_pages: int = Field(..., ge=0)
    checksum: str | None = Field(default=None, description="SHA-256 — feeds the duplicate-upload check (§1 step 1).")
    status: Literal["pending", "processing", "success", "failed"] = Field(
        default="pending",
        description="Ingestion state — mirrors the `ingestion_status` table.",
    )
    error_message: str | None = Field(default=None, description="Populated when status='failed'.")
    deleted_at: datetime | None = Field(default=None, description="Soft-delete timestamp, for audit integrity.")
    metadata: dict[str, Any] = Field(default_factory=dict)