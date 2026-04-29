"""FastAPI application entry point."""
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

# Demo project — allow all origins so Vercel preview URLs are never blocked.
# allow_credentials must be False when allow_origins=["*"] (CORS spec).
# Auth is handled via Bearer token in the Authorization header, not cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(listings.router, prefix="/api/listings", tags=["Listings"])
app.include_router(wishlist.router, prefix="/api/wishlist", tags=["Wishlist"])
app.include_router(orders.router,   prefix="/api/orders",   tags=["Orders"])


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "yugioh-store-api"}
