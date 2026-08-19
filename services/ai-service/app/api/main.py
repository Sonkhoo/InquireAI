"""
Main FastAPI application for InquireAI AI Service.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import chat, health
from app.logging import logfire

# Create FastAPI app
app = FastAPI(
    title="InquireAI",
    description="AI-powered document retrieval and chat service",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(chat.router)


@app.on_event("startup")
async def startup_event():
    """Log startup."""
    logfire.info("InquireAI AI Service started")


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown."""
    logfire.info("InquireAI AI Service stopped")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
