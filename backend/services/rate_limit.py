"""Rate limiting (AUDIT.md H2).

There was no limiter of any kind, and no reverse proxy in front of the app. A single
valid token could insert unbounded rows into a free-tier Postgres until it filled.

Limits are keyed per caller rather than globally, so one abusive client cannot deny
service to everyone else. Writes that create rows are limited hardest.
"""
import hashlib
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def client_key(request: Request) -> str:
    """Bucket by session when authenticated, by IP otherwise.

    The token is hashed, never stored or logged, and deliberately not verified --
    this is only a bucket label, so an invalid token simply gets its own bucket
    rather than sharing the caller's IP bucket.

    Keying on the caller matters for correctness as well as fairness: behind a
    shared IP (office NAT, mobile carrier), an IP-keyed limit would throttle
    unrelated users together.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
        if token:
            return "tok:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
    return "ip:" + (get_remote_address(request) or "unknown")


# Per-minute budgets, overridable so a deployment can tighten them without a
# code change. Defaults are deliberately generous enough for real use and far
# below what a scripted abuser wants.
ORDERS_PER_MIN = os.getenv("RATE_LIMIT_ORDERS_PER_MIN", "5")
WISHLIST_PER_MIN = os.getenv("RATE_LIMIT_WISHLIST_PER_MIN", "10")
LISTINGS_WRITE_PER_MIN = os.getenv("RATE_LIMIT_LISTINGS_PER_MIN", "30")
DEFAULT_PER_MIN = os.getenv("RATE_LIMIT_DEFAULT_PER_MIN", "300")

ORDER_LIMIT = f"{ORDERS_PER_MIN}/minute"
WISHLIST_LIMIT = f"{WISHLIST_PER_MIN}/minute"
LISTINGS_WRITE_LIMIT = f"{LISTINGS_WRITE_PER_MIN}/minute"

limiter = Limiter(
    key_func=client_key,
    default_limits=[f"{DEFAULT_PER_MIN}/minute"],
    # Deliberately off. With headers_enabled, slowapi injects X-RateLimit-* into the
    # endpoint's return value and requires it to be a starlette Response -- but these
    # endpoints return plain dicts for FastAPI to serialise, so it raises
    # "parameter `response` must be an instance of starlette.responses.Response"
    # on every limited call. Retry-After is set on the 429 below instead, which is
    # the header clients actually need.
    headers_enabled=False,
)


def _retry_after_seconds(exc: RateLimitExceeded) -> int:
    """Window length of the limit that was hit; 60 if it cannot be determined."""
    try:
        return int(exc.limit.limit.GRANULARITY.seconds)
    except Exception:  # pragma: no cover - defensive against slowapi internals
        return 60


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 in the same {"detail": ...} shape as the rest of the API."""
    response = JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Please retry shortly."},
    )
    response.headers["Retry-After"] = str(_retry_after_seconds(exc))
    return response
