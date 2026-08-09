"""JWT verification helpers for FastAPI dependency injection."""
import logging
from typing import Optional

import httpx
from fastapi import Depends, Header, HTTPException
from supabase_auth.errors import AuthApiError, AuthError, AuthRetryableError

from services.supabase_client import supabase

logger = logging.getLogger(__name__)

# One fixed message for every way a token can be bad: malformed, wrong signature,
# expired, revoked. The caller learns only that the token did not work, which is
# all they are entitled to know before authenticating (AUDIT.md M3). The real
# cause goes to the server log.
INVALID_TOKEN_DETAIL = "Invalid or expired token"
NOT_AUTHENTICATED_DETAIL = "Not authenticated"
ADMIN_REQUIRED_DETAIL = "Admin access required"

# Deliberately its own string rather than the one above. M3's oracle concern is
# that a caller must not learn *which* property of a token was wrong; this
# message is returned whatever the caller sent -- including a perfectly valid
# token -- so it discriminates nothing and closes no gap by differing. Saying
# "invalid token" during an outage would instead misdirect whoever is debugging
# it, and tell clients to re-authenticate when re-authenticating cannot work.
UNAVAILABLE_DETAIL = "Authentication temporarily unavailable"

# For a bug on our side rather than a verdict on the token or a known outage.
# Claiming the token was invalid would misdirect the same way, and "temporarily
# unavailable" would promise a retry that may never succeed. It says only that
# authentication did not complete, which is the one thing we actually know.
AUTH_FAILED_DETAIL = "Authentication failed"

# How long a client should wait before retrying a verification we could not make.
RETRY_AFTER_SECONDS = "5"


def _unavailable(exc: Exception) -> HTTPException:
    """503 for a verification that could not be made, as opposed to one that failed.

    Carries its own detail (see UNAVAILABLE_DETAIL) and Retry-After, neither of
    which says anything about the token. The exception text never reaches the
    client -- it can name internal hosts and ports -- and goes to the log at
    error level instead: this is our problem, not the caller's, and it should be
    as loud as one.
    """
    logger.error(
        "auth verification unavailable: %s: %s",
        type(exc).__name__, exc,
        exc_info=True,
    )
    return HTTPException(
        status_code=503,
        detail=UNAVAILABLE_DETAIL,
        headers={"Retry-After": RETRY_AFTER_SECONDS},
    )


def get_current_user(authorization: Optional[str] = Header(None)):
    """Verify the Bearer token from the Authorization header using Supabase Auth."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    token = authorization.split(" ", 1)[1]
    logger.info("get_current_user: verifying token (len=%d)", len(token))

    # "This token is not valid" and "I could not find out whether this token is
    # valid" are different facts, and only the first is about the caller. Reporting
    # an outage as 401 tells clients to re-authenticate, which cannot help and will
    # fail again, and hides the outage from every dashboard: a Supabase failure
    # renders as a wall of 401s rather than 5xx, so nothing alerts and nothing
    # scales. /health will not catch it either -- it deliberately never touches
    # Supabase, so it stays green throughout.
    #
    # M3 still holds. Its oracle concern is that a caller must not learn *which*
    # property of a token was wrong, so every 401 below carries one fixed string.
    # The 503 carries a different one, and that leaks nothing: it is returned
    # whatever the caller sent -- a valid token included -- so it partitions no
    # set of tokens and answers no question an attacker can ask.
    try:
        response = supabase.auth.get_user(token)
    except AuthRetryableError as exc:
        # supabase_auth's own "upstream is unwell" class: 502/503/504/520-524/530,
        # plus status 0 for its non-HTTPStatusError path.
        raise _unavailable(exc) from exc
    except AuthApiError as exc:
        # Supabase answered, so the round trip worked. A 4xx is a real verdict on
        # the token. A 5xx is Supabase reporting its own failure -- an outage
        # wearing an auth exception, and 500 specifically is not in the retryable
        # list above, so it only gets classified correctly here.
        if exc.status and exc.status >= 500:
            raise _unavailable(exc) from exc
        logger.warning(
            "token rejected: %s: status=%s: %s",
            type(exc).__name__, exc.status, exc,
        )
        raise HTTPException(status_code=401, detail=INVALID_TOKEN_DETAIL) from exc
    except AuthError as exc:
        # The remaining auth-layer errors (invalid JWT, missing session) are all
        # verdicts on the token rather than transport problems.
        logger.warning("token rejected: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=401, detail=INVALID_TOKEN_DETAIL) from exc
    except httpx.HTTPError as exc:
        # Never reached the service, so there is no verdict to report. gotrue only
        # converts HTTPStatusError and RuntimeError, so genuine transport failures
        # -- ConnectError, ReadTimeout, RemoteProtocolError, PoolTimeout -- arrive
        # here as themselves.
        raise _unavailable(exc) from exc
    except Exception as exc:
        # An exception we did not anticipate is a bug here, not a judgement on the
        # caller. Still fails closed: no user is returned either way.
        logger.error(
            "unexpected error verifying token: %s: %s",
            type(exc).__name__, exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=AUTH_FAILED_DETAIL) from exc

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
