"""JWT verification helpers for FastAPI dependency injection."""
import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException

from services.supabase_client import supabase

logger = logging.getLogger(__name__)

# One fixed message for every way a token can be bad: malformed, wrong signature,
# expired, revoked, or the auth service being unreachable. The caller learns only
# that the token did not work, which is all they are entitled to know before
# authenticating (AUDIT.md M3). The real cause goes to the server log.
INVALID_TOKEN_DETAIL = "Invalid or expired token"
NOT_AUTHENTICATED_DETAIL = "Not authenticated"
ADMIN_REQUIRED_DETAIL = "Admin access required"


def get_current_user(authorization: Optional[str] = Header(None)):
    """Verify the Bearer token from the Authorization header using Supabase Auth."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    token = authorization.split(" ", 1)[1]
    logger.info("get_current_user: verifying token (len=%d)", len(token))

    try:
        response = supabase.auth.get_user(token)
    except Exception as exc:
        # Full detail server-side only. This covers both "the token is bad" and
        # "Supabase is unreachable", which look identical to the client on purpose:
        # distinguishing them is exactly the oracle M3 is about.
        logger.warning(
            "token verification failed: %s: %s",
            type(exc).__name__, exc,
            exc_info=True,
        )
        raise HTTPException(status_code=401, detail=INVALID_TOKEN_DETAIL) from exc

    if not response or not response.user:
        logger.warning("token verification returned no user")
        raise HTTPException(status_code=401, detail=INVALID_TOKEN_DETAIL)

    logger.info("authenticated: user_id=%s", response.user.id)
    return response.user


def get_admin_user(user=Depends(get_current_user)):
    """Extend get_current_user: also assert the user has role='admin' in profiles."""
    try:
        # .limit(1) rather than .single(): .single() raises when 0 rows are found,
        # and that exception used to escape as a 404.
        result = (
            supabase.table("profiles")
            .select("role")
            .eq("id", user.id)
            .limit(1)
            .execute()
        )
        role = result.data[0].get("role") if result.data else None
    except Exception as exc:
        # Fail closed, and say nothing about why.
        logger.error(
            "profiles role lookup failed for user %s: %s: %s",
            user.id, type(exc).__name__, exc,
            exc_info=True,
        )
        raise HTTPException(status_code=403, detail=ADMIN_REQUIRED_DETAIL) from exc

    if role != "admin":
        logger.info("admin check denied: user=%s role=%s", user.id, role)
        raise HTTPException(status_code=403, detail=ADMIN_REQUIRED_DETAIL)

    logger.info("admin check passed: user=%s", user.id)
    return user
