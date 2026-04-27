"""Orders router — all endpoints require authentication."""
from fastapi import APIRouter, Depends
from services.supabase_client import supabase
from services.auth import get_current_user
from models.order import OrderCreate

router = APIRouter()


@router.get("/")
def get_orders(user=Depends(get_current_user)):
    """Return all orders for the authenticated user, newest first."""
    result = (
        supabase.table("orders")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.post("/", status_code=201)
def create_order(order: OrderCreate, user=Depends(get_current_user)):
    """Persist a mock checkout order and return the saved record."""
    data = {
        "user_id": user.id,
        "items": order.items,
        "total": order.total,
    }
    result = supabase.table("orders").insert(data).execute()
    return result.data[0]
