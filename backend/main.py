"""FastAPI application entry point."""
import os
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from routers import listings, wishlist, orders

load_dotenv()

app = FastAPI(
    title="Yu-Gi-Oh! Duel Market API",
    description="Backend for the YGO e-commerce demo. Card data comes from YGOPRODeck.",
    version="1.0.0",
)

# Prevent Railway's Fastly CDN from caching any API responses
class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

app.add_middleware(NoCacheMiddleware)

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
