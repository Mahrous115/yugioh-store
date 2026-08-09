"""Step 9 — stock is real, and decrements atomically (AUDIT.md L8).

`listings.stock` was displayed and gated the Add-to-Cart button client-side, but
placing an order never touched it. Orders were also written with no transaction
spanning a stock check, so even a correct implementation on top of the old code would
have raced.

The interesting test here is the oversell one: several buyers hitting the last few
units at the same moment. Sequential checks pass that test by luck, not design.
"""
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from conftest import SUPABASE_URL, _service_headers


# Every test here drives the running backend and a live Supabase project.
pytestmark = pytest.mark.integration

# temp_listing now lives in conftest.py so every suite can buy without
# draining the real catalogue.


def _stock_of(card_id):
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/listings?card_id=eq.{card_id}&select=stock",
        headers=_service_headers(),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()[0]["stock"]


def _order(api, user, card_id, quantity, **extra):
    return httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [{"card_id": card_id, "quantity": quantity}], **extra},
        timeout=30,
    )


# ── Stock actually moves ─────────────────────────────────────────────────────

def test_purchase_decrements_stock(api, make_user, temp_listing):
    listing = temp_listing(stock=10)
    user = make_user()

    r = _order(api, user, listing["card_id"], 3)
    assert r.status_code == 201, f"order failed: {r.text[:200]}"
    assert _stock_of(listing["card_id"]) == 7, "stock was not decremented"


def test_buying_the_last_unit_leaves_zero(api, make_user, temp_listing):
    listing = temp_listing(stock=2)
    user = make_user()

    assert _order(api, user, listing["card_id"], 2).status_code == 201
    assert _stock_of(listing["card_id"]) == 0


# ── Over-ordering is refused ─────────────────────────────────────────────────

def test_order_exceeding_stock_is_rejected(api, make_user, temp_listing):
    listing = temp_listing(stock=2)
    user = make_user()

    r = _order(api, user, listing["card_id"], 5)
    assert r.status_code == 409, f"expected 409 Conflict, got {r.status_code}: {r.text[:200]}"
    assert _stock_of(listing["card_id"]) == 2, "a rejected order still moved stock"


def test_out_of_stock_item_cannot_be_bought(api, make_user, temp_listing):
    listing = temp_listing(stock=0)
    user = make_user()

    r = _order(api, user, listing["card_id"], 1)
    assert r.status_code == 409
    assert _stock_of(listing["card_id"]) == 0


def test_rejection_names_the_card(api, make_user, temp_listing):
    """A shopper needs to know which line failed, not just that something did."""
    listing = temp_listing(stock=1)
    user = make_user()

    r = _order(api, user, listing["card_id"], 4)
    assert r.status_code == 409
    assert listing["card_name"] in r.json()["detail"], (
        f"error does not identify the card: {r.json()['detail']!r}"
    )


# ── Atomicity across a multi-line order ──────────────────────────────────────

def test_one_bad_line_rolls_back_the_whole_order(api, make_user, temp_listing):
    """Partial fulfilment would be worse than refusing outright."""
    plenty = temp_listing(stock=10)
    scarce = temp_listing(stock=1)
    user = make_user()

    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [
            {"card_id": plenty["card_id"], "quantity": 2},
            {"card_id": scarce["card_id"], "quantity": 5},   # not available
        ]},
        timeout=30,
    )
    assert r.status_code == 409, f"expected rejection, got {r.status_code}"
    assert _stock_of(plenty["card_id"]) == 10, (
        "the in-stock line was decremented even though the order failed -- "
        "the two writes are not in one transaction"
    )
    assert _stock_of(scarce["card_id"]) == 1

    orders = httpx.get(f"{api}/api/orders/", headers=user.api_headers, timeout=30).json()
    assert orders == [], "a rejected order was still persisted"


def test_total_mismatch_rolls_back_stock(api, make_user, temp_listing):
    """The C2 check must not leave stock spent on an order that never happened."""
    listing = temp_listing(stock=5, price=3.50)
    user = make_user()

    r = _order(api, user, listing["card_id"], 2, total=0.01)
    assert r.status_code == 400, f"forged total not rejected: {r.status_code}"
    assert _stock_of(listing["card_id"]) == 5, "stock moved despite the order being refused"


# ── The race ─────────────────────────────────────────────────────────────────

def test_concurrent_buyers_cannot_oversell(api, make_user, temp_listing):
    """Four buyers, two units, all at once. Exactly two may win.

    This is the test a non-transactional implementation fails: a check-then-write
    lets every request read stock=2 before any of them writes.
    """
    listing = temp_listing(stock=2)
    buyers = [make_user() for _ in range(4)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda u: _order(api, u, listing["card_id"], 1).status_code,
            buyers,
        ))

    succeeded = results.count(201)
    assert succeeded == 2, (
        f"{succeeded} of 4 concurrent buyers got the 2 available units: {results}. "
        "Anything above 2 is an oversell."
    )
    assert _stock_of(listing["card_id"]) == 0, "stock did not settle at zero"


# ── Nothing else regressed ───────────────────────────────────────────────────

def test_unlisted_card_still_400_not_409(api, make_user):
    """"Does not exist" and "not enough left" are different answers."""
    user = make_user()
    r = _order(api, user, 999_999_999, 1)
    assert r.status_code == 400, f"expected 400 for an unlisted card, got {r.status_code}"


def test_server_still_prices_the_order(api, make_user, temp_listing):
    listing = temp_listing(stock=10, price=3.50)
    user = make_user()

    r = _order(api, user, listing["card_id"], 2)
    assert r.status_code == 201
    assert float(r.json()["total"]) == 7.00, f"server mispriced the order: {r.json()['total']}"
