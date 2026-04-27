"""Wishlist router — all endpoints require authentication."""
from fastapi import APIRouter, Depends, HTTPException
from services.supabase_client import supabase
from services.auth import get_current_user
from models.wishlist import WishlistItemCreate

router = APIRouter()


@router.get("/")
def get_wishlist(user=Depends(get_current_user)):
    """Return all wishlist items for the authenticated user."""
    result = (
        supabase.table("wishlists")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.post("/", status_code=201)
def add_to_wishlist(item: WishlistItemCreate, user=Depends(get_current_user)):
    """Add a card to the user's wishlist (idempotent — 400 if already exists)."""
    existing = (
        supabase.table("wishlists")
        .select("id")
        .eq("user_id", user.id)
        .eq("card_id", item.card_id)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=400, detail="Card already in wishlist")

    data = {"user_id": user.id, **item.model_dump()}
    result = supabase.table("wishlists").insert(data).execute()
    return result.data[0]


@router.delete("/{card_id}", status_code=204)
def remove_from_wishlist(card_id: int, user=Depends(get_current_user)):
    """Remove a card from the user's wishlist by card_id."""
    supabase.table("wishlists").delete().eq("user_id", user.id).eq("card_id", card_id).execute()
