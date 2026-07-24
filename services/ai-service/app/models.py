"""
API Requests and Response models for the AI service.
Pydantic models for request validation and response serialization.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone

class ChatRequest(BaseModel):
    """
    Model for incoming chat requests.
    """
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000, 
        description="The input message for the AI model."
    )
    thread_id: str = Field(
        default = "default",
        description="The unique identifier for the conversation thread."
    )
    prompt: str = Field(
        ..., 
        description="The input prompt for the AI model."
    )

class ChatResponse(BaseModel):
    """
    Model for chat responses.
    """
    thread_id: str = Field(
        default = "default",
        description="The unique identifier for the conversation thread."
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
    token_usage: Optional[dict] = Field(
        default=None,
        description="Optional field to include token usage information."
    )
    cached: bool = Field(
        default=False,
        description="Indicates whether the response was served from cache."
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="The timestamp of the response in ISO 8601 format."
    )

class HealthCheckResponse(BaseModel):
    """
    Model for health check responses.
    """
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
        description="The timestamp of the health check in ISO 8601 format."
    )
    version: str = Field(
        default="1.0.0", 
        description="The version of the AI service."
    )
    environment: str = Field(
        default="development", 
        description="The environment in which the service is running."
    )
    checks: Optional[List[dict]] = Field(
        default=None,
        description="Optional detailed checks for various components of the service."
    )

class ErrorResponse(BaseModel):
    """
    Model for error responses.
    """
    error: str = Field(..., description="The error message.")
    code: Optional[int] = Field(None, description="Optional error code.")

