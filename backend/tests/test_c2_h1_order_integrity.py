"""Step 3 — order totals must come from the catalogue, not the customer.

AUDIT.md findings C2 and H1, both confirmed exploited on 2026-08-04:

  C2  POST /api/orders/ stored whatever `total` the body contained. 999 cards
      worth $5,984.01 were bought for $0.01. `items` was typed List[dict], so it
      accepted arbitrary JSON with no card, price, or quantity checking.

  H1  The orders_insert_own RLS policy let the browser INSERT into public.orders
      directly with the anon key, never touching FastAPI. Fixing only the API
      would have left this path wide open, so both are tested together.
"""
import httpx
import pytest

from conftest import SUPABASE_URL



# Every test here drives the running backend and a live Supabase project.
pytestmark = pytest.mark.integration

@pytest.fixture
def listing(temp_listing):
    """A disposable, well-stocked listing.

    These tests place real orders, and orders now decrement stock (migration 003),
    so they must not shop from the live catalogue.
    """
    return temp_listing(stock=1000, price=5.99)


def _item(listing, quantity=1, price=None):
    return {
        "card_id": listing["card_id"],
        "card_name": listing["card_name"],
        "card_image": listing["card_image"],
        "price": listing["price"] if price is None else price,
        "quantity": quantity,
    }


# ── C2: the server must own the arithmetic ───────────────────────────────────

def test_audit_exploit_999_cards_for_one_cent_is_rejected(api, make_user, listing):
    """The exact request from AUDIT.md C2, which previously returned 201.

    Any rejection is a pass here. In practice the per-line quantity bound (max 99)
    catches this one before the total is ever recomputed, so it comes back 422
    rather than 400 -- the point is that it no longer succeeds.
    """
    user = make_user()

    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [_item(listing, quantity=999, price=0.01)], "total": 0.01},
        timeout=30,
    )

    assert r.status_code >= 400, (
        f"accepted the audit exploit (HTTP {r.status_code}). "
        f"999 x {listing['card_name']} is worth "
        f"${round(listing['price'] * 999, 2)}, not $0.01."
    )


def test_forged_cheap_total_within_quantity_bounds_is_rejected(api, make_user, listing):
    """The same forgery scaled to a legal quantity, so it reaches the total check.

    This is the one that exercises the server-side recomputation rather than the
    input bounds, and it must be a 400 from the mismatch branch.
    """
    user = make_user()

    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [_item(listing, quantity=50, price=0.01)], "total": 0.01},
        timeout=30,
    )

    assert r.status_code == 400, (
        f"accepted a forged total (HTTP {r.status_code}). "
        f"50 x {listing['card_name']} is worth "
        f"${round(listing['price'] * 50, 2)}, not $0.01."
    )


def test_total_is_recomputed_from_the_catalogue(api, make_user, listing):
    """Even a plausible-but-wrong total must not be stored verbatim."""
    user = make_user()
    correct = round(listing["price"] * 2, 2)

    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [_item(listing, quantity=2)], "total": correct - 1.00},
        timeout=30,
    )
    assert r.status_code == 400, f"accepted a total $1 below the real price (HTTP {r.status_code})"

    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [_item(listing, quantity=2)], "total": correct},
        timeout=30,
    )
    assert r.status_code == 201, f"rejected an honest order: {r.text[:200]}"
    assert float(r.json()["total"]) == correct


def test_line_item_price_is_ignored_in_favour_of_the_listing(api, make_user, listing):
    """A tampered per-item price must not influence what is charged."""
    user = make_user()
    honest = round(listing["price"] * 1, 2)

    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [_item(listing, quantity=1, price=0.01)], "total": honest},
        timeout=30,
    )
    assert r.status_code == 201, f"honest total with tampered line price rejected: {r.text[:200]}"
    assert float(r.json()["total"]) == honest, "line-item price leaked into the stored total"


def test_unknown_card_id_is_rejected(api, make_user):
    """You cannot order something that is not for sale."""
    user = make_user()
    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={
            "items": [{
                "card_id": 999999999,
                "card_name": "Not For Sale",
                "card_image": "https://example.invalid/x.jpg",
                "price": 1.00,
                "quantity": 1,
            }],
            "total": 1.00,
        },
        timeout=30,
    )
    assert r.status_code == 400, f"accepted an order for an unlisted card (HTTP {r.status_code})"


def test_client_may_omit_total_entirely(api, make_user, listing):
    """The server is authoritative, so `total` should be optional."""
    user = make_user()
    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [_item(listing, quantity=3)]},
        timeout=30,
    )
    assert r.status_code == 201, f"order without a client total rejected: {r.text[:200]}"
    assert float(r.json()["total"]) == round(listing["price"] * 3, 2)


# ── C2: items[] needs a real schema ──────────────────────────────────────────

def test_arbitrary_json_in_items_is_rejected(api, make_user):
    """items was List[dict]; junk went straight into JSONB."""
    user = make_user()
    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [{"anything": "at all", "nested": {"x": [1, 2, 3]}}], "total": 0.01},
        timeout=30,
    )
    assert r.status_code == 422, f"accepted unstructured items[] (HTTP {r.status_code})"


def test_empty_order_is_rejected(api, make_user):
    user = make_user()
    r = httpx.post(f"{api}/api/orders/", headers=user.api_headers,
                   json={"items": [], "total": 1.0}, timeout=30)
    assert r.status_code == 422, f"accepted an order with no items (HTTP {r.status_code})"


@pytest.mark.parametrize("quantity", [0, -5])
def test_non_positive_quantity_is_rejected(api, make_user, listing, quantity):
    user = make_user()
    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [_item(listing, quantity=quantity)], "total": 1.0},
        timeout=30,
    )
    assert r.status_code == 422, f"accepted quantity={quantity} (HTTP {r.status_code})"


def test_absurd_item_count_is_rejected(api, make_user, listing):
    """Unbounded items[] is a cheap way to bloat a free-tier database."""
    user = make_user()
    r = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [_item(listing) for _ in range(500)], "total": 1.0},
        timeout=30,
    )
    assert r.status_code == 422, f"accepted a 500-line order (HTTP {r.status_code})"


# ── H1: the backend must be the only way in ──────────────────────────────────

def test_browser_cannot_insert_orders_directly(api, make_user, listing):
    """The second path to C2, bypassing every server-side check."""
    user = make_user()
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/orders",
        headers={**user.rest_headers, "Prefer": "return=representation"},
        json={
            "user_id": user.id,
            "items": [{"card_id": 1, "card_name": "FORGED-DIRECT", "price": 0.01, "quantity": 1}],
            "total": 0.01,
        },
        timeout=30,
    )
    assert r.status_code >= 400, (
        f"anon key inserted an order straight into Postgres (HTTP {r.status_code}). "
        "Server-side validation is irrelevant if the browser can skip it."
    )


def test_users_can_still_read_their_own_orders(api, make_user, listing):
    """Closing the INSERT path must not break order history."""
    user = make_user()
    created = httpx.post(
        f"{api}/api/orders/",
        headers=user.api_headers,
        json={"items": [_item(listing, quantity=1)]},
        timeout=30,
    )
    assert created.status_code == 201, f"could not place order: {created.text[:200]}"

    r = httpx.get(f"{api}/api/orders/", headers=user.api_headers, timeout=30)
    assert r.status_code == 200
    assert any(o["id"] == created.json()["id"] for o in r.json()), "order missing from history"
