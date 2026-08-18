from fastapi import APIRouter
import logfire

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health():
    logfire.info("Health check endpoint called")
    return {"status": "healthy"}        
 

@router.get("/version")
async def version():
    logfire.info("Version endpoint called")
    return {"version": "1.0.0"}