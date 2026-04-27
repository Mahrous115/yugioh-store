"""JWT verification helpers for FastAPI dependency injection."""
from fastapi import HTTPException, Depends, Header
from typing import Optional
from services.supabase_client import supabase


def get_current_user(authorization: Optional[str] = Header(None)):
    """Verify the Bearer token from the Authorization header using Supabase Auth."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ", 1)[1]
    try:
        response = supabase.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return response.user
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def get_admin_user(user=Depends(get_current_user)):
    """Extend get_current_user: also assert the user has role='admin' in profiles."""
    result = (
        supabase.table("profiles")
        .select("role")
        .eq("id", user.id)
        .single()
        .execute()
    )
    if not result.data or result.data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
