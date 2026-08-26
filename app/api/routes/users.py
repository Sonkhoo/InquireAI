from app.memory.memory import get_all_users
from fastapi import APIRouter, HTTPException
router = APIRouter(prefix="/api/users", tags=["users"])
@router.get("/users")
def get_demo_users():
    try:
        return get_all_users()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/roles")
def get_all_roles():
    """Retrieve all unique roles from the users table."""
    try:
        users = get_all_users()
        roles = {user["role"] for user in users}
        return list(roles)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))