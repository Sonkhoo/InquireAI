"""
API request and response models for the AI service.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Model for incoming chat requests."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="The input message for the AI model.",
    )
    thread_id: str = Field(
        default="default",
        description="The unique identifier for the conversation thread.",
    )
    prompt: str = Field(
        ...,
        description="The input prompt for the AI model.",
    )


class ChatResponse(BaseModel):
    """Model for chat responses."""

    thread_id: str = Field(
        default="default",
        description="The unique identifier for the conversation thread.",
    )
    response: str = Field(
        ..., 
        description="The AI model's response to the input message."
        )
    model_used: str = Field(
        ..., 
        description="The name of the AI model used to generate the response."
        )
    processing_time: float = Field(
        ..., 
        description="The time taken to process the request in seconds."
        )
    token_usage: dict[str, Any] | None = Field(
        default=None,
        description="Optional field to include token usage information.",
    )
    cached: bool = Field(
        default=False,
        description="Indicates whether the response was served from cache.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="The timestamp of the response in ISO 8601 format.",
    )


class HealthCheckResponse(BaseModel):
    """Model for health check responses."""

    status: str = Field(
        default="healthy", 
        description="The health status of the service."
        )
    uptime: float = Field(
        ..., 
        description="The uptime of the service in seconds."
        )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="The timestamp of the health check in ISO 8601 format.",
    )
    version: str = Field(
        default="1.0.0", 
        description="The version of the AI service."
        )
    environment: str = Field(
        default="development", 
        description="The environment in which the service is running."
        )
    checks: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional detailed checks for various components of the service.",
    )


class ErrorResponse(BaseModel):
    """Model for error responses."""

    error: str = Field(
        ..., 
        description="The error message."
        )
    code: int | None = Field(
        default=None, 
        description="Optional error code."
        )


class ChunkMetadata(BaseModel):
    file_id: str = Field(
        ..., 
        description="The unique identifier of the source file."
        )
    workspace_id: str = Field(
        ..., 
        description="The workspace that owns the chunk."
        )
    filename: str = Field(
        ..., 
        description="The source filename."
        )
    allowed_role_ids: list[str] = Field(
        default_factory=list, 
        description="Roles allowed to read the chunk."
        )
    chunk_index: int = Field(
        ..., 
        ge=0, 
        description="The zero-based index of the chunk within the document."
        )
    page_start: int | None = Field(
        default=None, 
        ge=1, 
        description="First page covered by the chunk."
        )
    page_end: int | None = Field(
        default=None, 
        ge=1, 
        description="Last page covered by the chunk."
        )
    section_title: str | None = Field(
        default=None, 
        description="Section title associated with the chunk."
        )
    token_count: int = Field(
        ..., 
        ge=0, 
        description="Token count for the chunk text."
        )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the chunk metadata was created.",
    )


class Chunk(BaseModel):
    id: str = Field(
        ..., 
        description="The unique chunk identifier.")
    text: str = Field(
        ..., 
        description="The chunk text."
        )
    chunk_index: int = Field(
        ..., 
        ge=0, 
        description="The zero-based chunk index."
        )
    page_start: int | None = Field(
        default=None, 
        ge=1, 
        description="First page covered by the chunk."
        )
    page_end: int | None = Field(
        default=None, 
        ge=1, 
        description="Last page covered by the chunk."
        )
    embedding: list[float] | None = Field(
        default=None, 
        description="Optional embedding vector."
        )
    metadata: ChunkMetadata = Field(
        ..., 
        description="Chunk metadata."
        )


class Document(BaseModel):
    id: str = Field(
        ..., 
        description="The unique document identifier."
        )
    filename: str = Field(
        ..., 
        description="The original filename."
        )
    file_type: str = Field(
        ..., 
        description="The document file type, such as pdf."
        )
    workspace_id: str = Field(
        ..., 
        description="The workspace that owns the document."
        )
    storage_key: str = Field(
        ..., 
        description="The storage location key."
        )
    uploaded_at: datetime = Field(
        ..., 
        description="When the document was uploaded."
        )
    total_pages: int = Field(
        ..., 
        ge=0, 
        description="Total number of pages in the document."
        )
    checksum: str | None = Field(
        default=None, 
        description="Optional document checksum."
        )
    metadata: dict[str, Any] = Field(
        default_factory=dict, 
        description="Extra document metadata."
        )
