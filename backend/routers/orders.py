"""Orders router — all endpoints require authentication."""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request

from models.order import OrderCreate
from services.auth import get_current_user
from services.rate_limit import ORDER_LIMIT, limiter
from services.supabase_client import supabase

router = APIRouter()
logger = logging.getLogger(__name__)


def _translate_place_order_error(message: str) -> HTTPException:
    """Map a sentinel raised by public.place_order onto an HTTP response.

    Pricing, stock and validation all live inside the function so they share one
    transaction (AUDIT.md C2 and L8). The trade-off is that failures arrive as
    Postgres exception strings and have to be translated back here.
    """
    if match := re.search(r"NOT_LISTED:(\d+)", message):
        return HTTPException(
            status_code=400,
            detail=f"Card {match.group(1)} is not available for purchase.",
        )

    if match := re.search(r"INSUFFICIENT_STOCK:(\d+):(\d+):(.*)", message, re.DOTALL):
        available, requested, card_name = match.groups()
        return HTTPException(
            status_code=409,  # a conflict with current state, not a malformed request
            detail=(
                f'Not enough stock for "{card_name.strip()}": '
                f"{requested} requested, {available} available."
            ),
        )

    if match := re.search(r"TOTAL_MISMATCH:([\d.]+):([\d.]+)", message):
        computed, given = match.groups()
        return HTTPException(
            status_code=400,
            detail=(
                f"Order total mismatch: got {given}, expected {computed}. "
                "Prices may have changed — refresh your cart and try again."
            ),
        )

    if "EMPTY_ORDER" in message:
        return HTTPException(status_code=422, detail="An order must contain at least one item.")

    if match := re.search(r"BAD_QUANTITY:(\d+)", message):
        return HTTPException(
            status_code=422,
            detail=f"Invalid quantity for card {match.group(1)}.",
        )

    return None


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
@limiter.limit(ORDER_LIMIT)  # tightest budget in the app: every call creates a row
def create_order(request: Request, order: OrderCreate, user=Depends(get_current_user)):
    """Place an order: price it, reserve stock, and record it — atomically.

    The work happens in public.place_order rather than here. PostgREST cannot span
    statements in a transaction, and reserving stock is exactly the operation that
    must not be split: a check-then-write in Python lets concurrent buyers all read
    the same remaining stock and every one of them succeed.

    Inside that function each listing row is locked with SELECT ... FOR UPDATE, the
    price and total are read from the locked rows, and any failure rolls back every
    decrement made earlier in the call. `user_id` still comes from the verified
    token, never the body.
    """
    payload = {
        "p_user_id": user.id,
        "p_items": [item.model_dump() for item in order.items],
        # Optional and never authoritative -- only used to detect a client that
        # disagrees about the price, so a real bug fails loudly (AUDIT.md C2).
        "p_expected_total": order.total,
    }

    try:
        result = supabase.rpc("place_order", payload).execute()
    except Exception as exc:
        # postgrest's APIError carries the raw RAISE text on .message; str(exc) is a
        # dict repr, and parsing a trailing card name out of that swallows the
        # surrounding "', 'code': 'P0001', ...}" too.
        raw = getattr(exc, "message", None) or str(exc)
        translated = _translate_place_order_error(raw)
        if translated is not None:
            raise translated from exc
        # An unrecognised database failure is a server-side problem, and its text
        # does not go to the client (AUDIT.md M3).
        logger.error("place_order failed for user %s: %s", user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not place order.") from exc

    if not result.data:  # pragma: no cover - defensive
        logger.error("place_order returned no row for user %s", user.id)
        raise HTTPException(status_code=500, detail="Could not place order.")

    return result.data
