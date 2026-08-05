"""FastAPI application entry point."""
import logging
import os
import re
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from routers import listings, wishlist, orders
from services.rate_limit import limiter, rate_limit_exceeded_handler

# In a container there is no .env file; the platform injects real environment
# variables. load_dotenv() does not overwrite variables that are already set, so
# this stays useful locally and is a no-op in production.
load_dotenv()


# ─── Logging ─────────────────────────────────────────────────────────────────
#
# Explicitly to stdout. Nothing in this app writes log files, and a container must
# not start: the platform collects stdout/stderr, and a file inside the container
# is lost when it restarts and invisible while it runs.
#
# Without this, app loggers inherit the root default of WARNING, so every
# logger.info() in the codebase was silently discarded.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    stream=sys.stdout,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    force=True,   # replace anything a dependency configured first
)

logger = logging.getLogger(__name__)

# Interactive docs publish a complete map of every endpoint, parameter and model.
# Useful locally, pure reconnaissance value in production, so they are off unless
# explicitly switched on (AUDIT.md M4). Only an affirmative value opens them --
# unset, empty, "false", "0" and "no" all leave them shut.
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "").strip().lower() in ("1", "true", "yes", "on")

API_TITLE = os.getenv("API_TITLE", "Yu-Gi-Oh! Duel Market API")
API_VERSION = os.getenv("API_VERSION", "1.0.0")

app = FastAPI(
    title=API_TITLE,
    description="Backend for the YGO e-commerce demo. Card data comes from YGOPRODeck.",
    version=API_VERSION,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    # Closing this alone would disable /docs and /redoc too, since they fetch it;
    # all three are set explicitly so the intent survives someone editing one.
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)

# This service answers with JSON, never HTML, so it can afford the strictest CSP
# there is. That matters beyond tidiness: a CSP is the mitigation that contains an
# XSS, and session tokens live in localStorage (AUDIT.md H3).
API_CSP = (
    "default-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

# Swagger UI is HTML with inline styles and CDN assets, so deny-all would render a
# blank page. Relaxed only as far as it needs to be, and still unframeable.
DOCS_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)

DOCS_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers on every response, including errors.

    Also carries the Cache-Control/Pragma pair that used to live in
    NoCacheMiddleware. That was added to defeat Railway's Fastly CDN, which is gone,
    but no-store is still the right default for authenticated JSON.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Ignored by browsers over plain http, so it costs nothing locally and is
        # correct the moment this is served over TLS.
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        response.headers["Content-Security-Policy"] = (
            DOCS_CSP if request.url.path in DOCS_PATHS else API_CSP
        )
        return response


# ─── Rate limiting ───────────────────────────────────────────────────────────
#
# Registered BEFORE SecurityHeadersMiddleware on purpose. Starlette applies the
# last-added middleware outermost, so adding the limiter first leaves it inside the
# header middleware -- which means a 429 generated here still travels back out
# through it and carries the security headers (AUDIT.md M5).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(SecurityHeadersMiddleware)

# ─── CORS ────────────────────────────────────────────────────────────────────
#
# This was allow_origins=["*"] so that Vercel preview URLs were never blocked.
# The need was real; the wildcard was not the way to meet it. See AUDIT.md M1.
#
# Everything here is environment-driven so that adding an origin -- an Azure
# Container Apps URL, a Static Web Apps URL, a new custom domain -- is a config
# change on the running revision, not a rebuild.

DEFAULT_DEV_ORIGIN = "http://localhost:5173"


def _split_origins(raw):
    """Comma-separated origins -> normalised list. Trailing slashes are dropped
    because the browser never sends one in the Origin header."""
    return [o.strip().rstrip("/") for o in (raw or "").split(",") if o.strip()]


# CORS_ALLOWED_ORIGINS is the intended knob. FRONTEND_URL is the older name and is
# still honoured -- it is set in existing .env files and documented in the README,
# and silently ignoring it would fail as "CORS is broken" with no clue why. Both
# are merged rather than one overriding the other, so setting either works.
_configured_origins = (
    _split_origins(os.getenv("CORS_ALLOWED_ORIGINS"))
    + _split_origins(os.getenv("FRONTEND_URL"))
)

# The local dev origin is always allowed: it is not a secret, it is not reachable
# from anywhere but the developer's own machine, and leaving it out is the single
# most common way to make local work mysteriously stop.
ALLOWED_ORIGINS = list(dict.fromkeys(_configured_origins + [DEFAULT_DEV_ORIGIN]))

# Preview deployments get a generated hostname per commit, so they cannot be
# enumerated ahead of time and have to be matched by pattern.
#
# Two ways to configure it, both defaulting to "no preview matching at all":
#
#   VERCEL_PROJECT_SLUG        convenience -- builds the standard Vercel pattern
#                              for one project. No default: this used to be
#                              hardcoded to a specific project's slug, which is
#                              deployment config living in source.
#
#   CORS_PREVIEW_ORIGIN_REGEX  escape hatch -- a full regex, for any other host
#                              (Azure Static Web Apps, Netlify, a custom scheme).
#                              Takes precedence when both are set.
#
# The generated pattern is anchored at both ends and https-only, so none of these
# get through: https://evil-<slug>.vercel.app (prefix smuggling),
# https://<slug>.vercel.app.evil.com (suffix smuggling), http://<slug>.vercel.app
# (downgraded scheme). A hand-written regex must anchor itself.
VERCEL_PROJECT_SLUG = os.getenv("VERCEL_PROJECT_SLUG", "").strip()
_preview_regex = os.getenv("CORS_PREVIEW_ORIGIN_REGEX", "").strip()

if not _preview_regex and VERCEL_PROJECT_SLUG:
    _preview_regex = (
        rf"^https://{re.escape(VERCEL_PROJECT_SLUG)}(-[a-z0-9-]+)?\.vercel\.app$"
    )

PREVIEW_ORIGIN_REGEX = _preview_regex or None

if PREVIEW_ORIGIN_REGEX:
    # Fail at startup rather than serving with a pattern that never matches.
    try:
        re.compile(PREVIEW_ORIGIN_REGEX)
    except re.error as exc:
        raise RuntimeError(
            f"CORS_PREVIEW_ORIGIN_REGEX is not a valid regular expression: {exc}"
        ) from exc

logger.info(
    "CORS: %d fixed origin(s); preview pattern %s",
    len(ALLOWED_ORIGINS),
    "configured" if PREVIEW_ORIGIN_REGEX else "not set",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=PREVIEW_ORIGIN_REGEX,
    # Stays False: auth is a Bearer token in the Authorization header, never a
    # cookie, so the browser has no ambient credential to attach. Nothing needs
    # credentialed CORS, and leaving it off keeps a hostile page from replaying a
    # session it does not already hold.
    allow_credentials=False,
    # Only what the API actually exposes, rather than "*".
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    # Retry-After is not a CORS-safelisted response header, so without this the
    # browser receives it and hides it from JS -- the cart could not tell a
    # rate-limited shopper how long to wait.
    expose_headers=["Retry-After"],
)

app.include_router(listings.router, prefix="/api/listings", tags=["Listings"])
app.include_router(wishlist.router, prefix="/api/wishlist", tags=["Wishlist"])
app.include_router(orders.router,   prefix="/api/orders",   tags=["Orders"])


# ─── Health ──────────────────────────────────────────────────────────────────
#
# Deliberately does NOT touch Supabase. A probe that checks the database conflates
# "this container is alive" with "a third party is reachable": a Supabase blip
# would make the platform kill and restart healthy replicas, turning a partial
# outage into a total one. Readiness of a dependency is a different question from
# liveness of the process, and this endpoint answers the second.
#
# Both routes are exempt from rate limiting -- a probe hitting a fixed endpoint
# every few seconds is exactly the traffic the limiter is built to reject, and a
# throttled 429 would read as an unhealthy container.

@app.get("/health", tags=["Health"])
@limiter.exempt
def health():
    """Liveness probe. 200 as long as the process is serving."""
    return {"status": "ok", "service": "yugioh-store-api"}


@app.get("/", tags=["Health"])
@limiter.exempt
def health_check():
    """Kept alongside /health: existing clients and tests use it."""
    return {"status": "ok", "service": "yugioh-store-api"}


# ─── Container entrypoint ────────────────────────────────────────────────────
#
# Lets the image run `python main.py` with no uvicorn flags to get wrong.
#
# Binding 0.0.0.0 is required: the default 127.0.0.1 only accepts connections from
# inside the container, so the platform's health probe and ingress cannot reach it
# and the revision never goes healthy.
#
# Azure Container Apps sets PORT to the configured target port. The 8000 default
# keeps `python main.py` working locally.
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    logger.info("starting uvicorn on 0.0.0.0:%d", port)
    uvicorn.run(
        app,
        host="0.0.0.0",   # noqa: S104 - intentional; see above
        port=port,
        log_level=LOG_LEVEL.lower(),
        # Behind the platform's ingress, so trust its forwarding headers for the
        # client IP the rate limiter buckets on.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
