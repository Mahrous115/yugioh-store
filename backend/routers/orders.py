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

    `message` is the verbatim RAISE text, so every pattern is anchored at the start
    with re.match rather than searched for anywhere in the string. Only the opening
    field may decide which sentinel this is. INSUFFICIENT_STOCK ends with card_name,
    which is free text: it may contain colons, newlines, quotes, and the spelling of
    any other sentinel. Searching let a card called "Foo NOT_LISTED:9" answer for the
    message it merely appeared in, turning its own 409 into a 400. That is also why
    card_name is last in the SQL format string -- every field ahead of it is numeric,
    so nothing a name contains can reach a capture group but its own.
    """
    if match := re.match(r"NOT_LISTED:(\d+)", message):
        return HTTPException(
            status_code=400,
            detail=f"Card {match.group(1)} is not available for purchase.",
        )

    # Greedy, DOTALL, and running to the end of the string on purpose: group 3 is the
    # whole remainder, so a name keeps its colons and newlines. `$` is avoided because
    # it would quietly drop a trailing newline from the name.
    if match := re.match(r"INSUFFICIENT_STOCK:(\d+):(\d+):(.*)", message, re.DOTALL):
        available, requested, card_name = match.groups()
        return HTTPException(
            status_code=409,  # a conflict with current state, not a malformed request
            detail=(
                f'Not enough stock for "{card_name.strip()}": '
                f"{requested} requested, {available} available."
            ),
        )

    if match := re.match(r"TOTAL_MISMATCH:([\d.]+):([\d.]+)", message):
        computed, given = match.groups()
        return HTTPException(
            status_code=400,
            detail=(
                f"Order total mismatch: got {given}, expected {computed}. "
                "Prices may have changed — refresh your cart and try again."
            ),
        )

    # The loosest of the five: a substring test matched EMPTY_ORDER anywhere at all.
    if message == "EMPTY_ORDER":
        return HTTPException(status_code=422, detail="An order must contain at least one item.")

    if match := re.match(r"BAD_QUANTITY:(\d+)", message):
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
        # Only postgrest's APIError.message carries the RAISE text verbatim. str(exc)
        # is a repr of the whole error dict, and a sentinel parsed out of that drags
        # the surrounding "', 'code': 'P0001', ...}" into the detail the client is
        # shown (AUDIT.md M3). So an exception carrying no .message is not a
        # place_order sentinel, whatever its repr happens to spell, and is not parsed
        # at all -- the guarantee sits at the source rather than resting on five
        # regexes staying tight. .message is Optional[str] in postgrest, so
        # present-but-None has to count as absent.
        #
        # The cost: were postgrest to stop exposing .message, every sentinel would
        # collapse to a flat 500 and out-of-stock would stop being a 409. That is a
        # visible, fail-closed regression instead of a silent leak; message=%r below
        # names it in the log, and tests/test_m3_order_error_translation.py pins the
        # attribute so a dependency bump fails there first.
        raw = getattr(exc, "message", None)
        translated = _translate_place_order_error(raw) if raw else None
        if translated is not None:
            raise translated from exc
        # An unrecognised database failure is a server-side problem, and its text
        # does not go to the client (AUDIT.md M3).
        logger.error(
            "place_order failed for user %s (message=%r): %s",
            user.id, raw, exc, exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Could not place order.") from exc

    if not result.data:  # pragma: no cover - defensive
        logger.error("place_order returned no row for user %s", user.id)
        raise HTTPException(status_code=500, detail="Could not place order.")

    return result.data
