import logfire
from fastapi import FastAPI
import uvicorn

app = FastAPI()

logfire.configure()
logfire.instrument_system_metrics()
logfire.instrument_fastapi(app)


@app.get("/health")
async def health():
    logfire.info("Health check endpoint called")
    return {"status": "healthy"}


@app.get("/version")
async def version():
    logfire.info("Version endpoint called")
    return {"version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)