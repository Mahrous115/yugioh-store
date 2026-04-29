"""JWT verification helpers for FastAPI dependency injection."""
import logging
from fastapi import HTTPException, Depends, Header
from typing import Optional
from services.supabase_client import supabase

logger = logging.getLogger(__name__)


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
        logger.error("get_user failed: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def get_admin_user(user=Depends(get_current_user)):
    """Extend get_current_user: also assert the user has role='admin' in profiles."""
    try:
        # Use .limit(1) instead of .single() — .single() raises when 0 rows are
        # found (PostgREST returns 404/406) and that exception escapes as a 404.
        result = (
            supabase.table("profiles")
            .select("role")
            .eq("id", user.id)
            .limit(1)
            .execute()
        )
        role = result.data[0].get("role") if result.data else None
    except Exception as exc:
        logger.error("profiles role check failed for user %s: %s (%r)", user.id, exc, exc)
        raise HTTPException(status_code=403, detail="Admin access required") from exc

    logger.debug("admin check: user=%s role=%s", user.id, role)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
