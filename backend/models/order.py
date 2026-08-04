from typing import List, Optional

from pydantic import BaseModel, Field


class OrderItemRequest(BaseModel):
    """A single requested line item.

    Deliberately minimal: only the card and how many. Name, image and price are
    NOT accepted from the client — the server reads them from the listings table
    when building the order, so a tampered request body cannot influence what is
    stored or charged (AUDIT.md C2).

    Pydantic ignores unknown fields by default, so the frontend may keep sending
    its full cart shape; the extra keys are simply dropped.
    """

    card_id: int
    quantity: int = Field(ge=1, le=99)


class OrderCreate(BaseModel):
    # Bounded so a single request cannot bloat the orders table.
    items: List[OrderItemRequest] = Field(min_length=1, max_length=50)

    # Optional, and never trusted. When supplied it is compared against the
    # server-computed total and a mismatch is rejected, so a genuine client bug
    # fails loudly instead of silently charging the wrong amount.
    total: Optional[float] = Field(default=None, ge=0)


class OrderItem(BaseModel):
    """The stored shape of a line item, built server-side from the listing."""

    card_id: int
    card_name: str
    card_image: str
    price: float
    quantity: int
