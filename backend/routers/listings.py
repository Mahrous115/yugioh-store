"""Listings router — public reads, admin-only writes."""
from fastapi import APIRouter, Depends, HTTPException
from services.supabase_client import supabase
from services.auth import get_admin_user
from models.listing import ListingCreate, ListingUpdate

router = APIRouter()


@router.get("/")
def get_listings():
    """Return all custom listings (public endpoint)."""
    result = supabase.table("listings").select("*").order("created_at", desc=True).execute()
    return result.data


@router.post("/", status_code=201)
def create_listing(listing: ListingCreate, _user=Depends(get_admin_user)):
    """Create a new listing. Admin only."""
    result = supabase.table("listings").insert(listing.model_dump()).execute()
    return result.data[0]


@router.put("/{listing_id}")
def update_listing(
    listing_id: str, update: ListingUpdate, _user=Depends(get_admin_user)
):
    """Update price and/or stock for an existing listing. Admin only."""
    changes = {k: v for k, v in update.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = (
        supabase.table("listings")
        .update(changes)
        .eq("id", listing_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Listing not found")
    return result.data[0]


@router.delete("/{listing_id}", status_code=204)
def delete_listing(listing_id: str, _user=Depends(get_admin_user)):
    """Delete a listing by ID. Admin only."""
    supabase.table("listings").delete().eq("id", listing_id).execute()
