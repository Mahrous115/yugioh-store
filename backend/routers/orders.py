"""Orders router — all endpoints require authentication."""
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Request

from models.order import OrderCreate
from services.auth import get_current_user
from services.rate_limit import ORDER_LIMIT, limiter
from services.supabase_client import supabase

router = APIRouter()

CENTS = Decimal("0.01")


def _money(value) -> Decimal:
    """Parse to 2dp Decimal. str() first: float('5.99') is not exactly 5.99."""
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


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
    """Persist a mock checkout order, priced from the catalogue.

    Nothing about the money comes from the request body. Each card_id is looked
    up in `listings`, the line items are rebuilt from that row, and the total is
    summed server-side. A client-supplied `total` is only ever used to detect a
    disagreement (AUDIT.md C2).
    """
    requested_ids = [item.card_id for item in order.items]

    result = (
        supabase.table("listings")
        .select("card_id, card_name, card_image, price")
        .in_("card_id", requested_ids)
        .execute()
    )
    listings_by_id = {row["card_id"]: row for row in result.data}

    unavailable = sorted(set(requested_ids) - set(listings_by_id))
    if unavailable:
        raise HTTPException(
            status_code=400,
            detail=f"These cards are not available for purchase: {unavailable}",
        )

    items = []
    computed_total = Decimal("0.00")
    for requested in order.items:
        listing = listings_by_id[requested.card_id]
        unit_price = _money(listing["price"])
        computed_total += unit_price * requested.quantity
        # Stored from the listing, not from the request.
        items.append({
            "card_id": listing["card_id"],
            "card_name": listing["card_name"],
            "card_image": listing["card_image"],
            "price": float(unit_price),
            "quantity": requested.quantity,
        })

    computed_total = computed_total.quantize(CENTS, rounding=ROUND_HALF_UP)

    if order.total is not None and _money(order.total) != computed_total:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Order total mismatch: got {_money(order.total)}, "
                f"expected {computed_total}. Prices may have changed — "
                "refresh your cart and try again."
            ),
        )

    data = {
        "user_id": user.id,       # from the verified token, never the body
        "items": items,           # rebuilt from the catalogue
        "total": float(computed_total),
    }
    result = supabase.table("orders").insert(data).execute()
    return result.data[0]
