"""FastAPI application entry point."""
import os
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from routers import listings, wishlist, orders
from services.rate_limit import limiter, rate_limit_exceeded_handler

load_dotenv()

# Interactive docs publish a complete map of every endpoint, parameter and model.
# Useful locally, pure reconnaissance value in production, so they are off unless
# explicitly switched on (AUDIT.md M4). Only an affirmative value opens them --
# unset, empty, "false", "0" and "no" all leave them shut.
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "").strip().lower() in ("1", "true", "yes", "on")

app = FastAPI(
    title="Yu-Gi-Oh! Duel Market API",
    description="Backend for the YGO e-commerce demo. Card data comes from YGOPRODeck.",
    version="1.0.0",
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
# FRONTEND_URL accepts a comma-separated list, so additional fixed origins can be
# added without a code change. Preview deployments are matched by pattern, since
# their hostnames are generated per commit and cannot be enumerated in advance.

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in FRONTEND_URL.split(",") if o.strip()]

# Matches this project's own Vercel deployments only:
#   https://project-4yktn.vercel.app                    (production)
#   https://project-4yktn-git-<branch>-<scope>.vercel.app
#   https://project-4yktn-<hash>.vercel.app
#
# Anchored at both ends and https-only, so none of these get through:
#   https://evil-project-4yktn.vercel.app       (prefix smuggling)
#   https://project-4yktn.vercel.app.evil.com   (suffix smuggling)
#   http://project-4yktn.vercel.app             (downgraded scheme)
VERCEL_PROJECT_SLUG = os.getenv("VERCEL_PROJECT_SLUG", "project-4yktn")
VERCEL_PREVIEW_REGEX = rf"^https://{re.escape(VERCEL_PROJECT_SLUG)}(-[a-z0-9-]+)?\.vercel\.app$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=VERCEL_PREVIEW_REGEX,
    # Stays False: auth is a Bearer token in the Authorization header, never a
    # cookie, so the browser has no ambient credential to attach. Nothing needs
    # credentialed CORS, and leaving it off keeps a hostile page from replaying a
    # session it does not already hold.
    allow_credentials=False,
    # Only what the API actually exposes, rather than "*".
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(listings.router, prefix="/api/listings", tags=["Listings"])
app.include_router(wishlist.router, prefix="/api/wishlist", tags=["Wishlist"])
app.include_router(orders.router,   prefix="/api/orders",   tags=["Orders"])


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "yugioh-store-api"}
