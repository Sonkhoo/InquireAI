from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logfire

from app.api.routes.chat import router as chat_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.upload import router as files_router
from app.api.routes.users import router as users_router
from app.logging import init_logging
from app.memory.memory import close_pool, open_pool

init_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    logfire.info("InquireAI AI Service started")
    try:
        yield
    finally:
        close_pool()
        logfire.info("InquireAI AI Service stopped")

app = FastAPI(
    title="InquireAI",
    description="AI-powered document retrieval and chat service",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Telemetry
logfire.instrument_system_metrics()
logfire.instrument_fastapi(app)

# Routes
app.include_router(health_router)
app.include_router(files_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(users_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)