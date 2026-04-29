"""FastAPI application entry point."""
import os
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

# Allow requests from the frontend (configure FRONTEND_URL in .env for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(listings.router, prefix="/api/listings", tags=["Listings"])
app.include_router(wishlist.router, prefix="/api/wishlist", tags=["Wishlist"])
app.include_router(orders.router,   prefix="/api/orders",   tags=["Orders"])


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "yugioh-store-api"}
