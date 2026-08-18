from fastapi import FastAPI
import uvicorn
import logfire

from app.logging import init_logging
from app.api.routes.health import router as health_router
from app.api.routes.upload import router as files_router
from app.api.routes.chat import router as chat_router

init_logging()

app = FastAPI()

logfire.instrument_system_metrics()
logfire.instrument_fastapi(app)

app.include_router(health_router)
app.include_router(files_router)
app.include_router(chat_router)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )