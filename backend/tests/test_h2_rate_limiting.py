"""Step 8 — write endpoints are rate limited (AUDIT.md H2).

There was no limiter, no reverse proxy, nothing. A single valid token could insert
unbounded rows into a free-tier Postgres until it filled. Supabase rate-limits its own
auth endpoints, so signup/login had some cover; this API had none.

Limits are keyed per caller (per token when authenticated, per IP otherwise) rather
than globally, so one abusive client cannot deny service to everyone else -- and so
that these tests do not interfere with the rest of the suite.
"""
import httpx
import pytest

from conftest import ORDER_LIMIT_PER_MIN, WISHLIST_LIMIT_PER_MIN


def _order_payload(listing):
    return {"items": [{"card_id": listing["card_id"], "quantity": 1}]}


def _wishlist_payload(card_id):
    return {
        "card_id": card_id,
        "card_name": f"Card {card_id}",
        "card_image": "https://example.invalid/x.jpg",
    }


def _hammer(fn, attempts):
    """Fire `attempts` requests, return the list of status codes."""
    return [fn(i).status_code for i in range(attempts)]


# ── Order creation: the tightest limit ───────────────────────────────────────

def test_order_creation_is_rate_limited(api, make_user, listings):
    user = make_user()
    listing = listings[0]
    codes = _hammer(
        lambda i: httpx.post(
            f"{api}/api/orders/", headers=user.api_headers,
            json=_order_payload(listing), timeout=30,
        ),
        ORDER_LIMIT_PER_MIN + 2,
    )
    assert 429 in codes, (
        f"placed {len(codes)} orders with no limit hit (limit is "
        f"{ORDER_LIMIT_PER_MIN}/min): {codes}"
    )
    assert codes[0] == 201, f"the first order should still succeed, got {codes[0]}"


def test_wishlist_writes_are_rate_limited(api, make_user):
    user = make_user()
    codes = _hammer(
        lambda i: httpx.post(
            f"{api}/api/wishlist/", headers=user.api_headers,
            json=_wishlist_payload(700000 + i), timeout=30,
        ),
        WISHLIST_LIMIT_PER_MIN + 2,
    )
    assert 429 in codes, (
        f"made {len(codes)} wishlist writes with no limit hit (limit is "
        f"{WISHLIST_LIMIT_PER_MIN}/min): {codes}"
    )


# ── Shape of the rejection ───────────────────────────────────────────────────

def test_429_is_well_formed(api, make_user, listings):
    user = make_user()
    listing = listings[0]
    response = None
    for _ in range(ORDER_LIMIT_PER_MIN + 2):
        r = httpx.post(f"{api}/api/orders/", headers=user.api_headers,
                       json=_order_payload(listing), timeout=30)
        if r.status_code == 429:
            response = r
            break
    assert response is not None, "never hit the limit"

    assert "retry-after" in response.headers, (
        "429 has no Retry-After; a well-behaved client cannot tell when to come back"
    )
    assert "detail" in response.json(), (
        f"429 body should match the API's error shape, got {response.text[:150]}"
    )


def test_429_still_carries_security_headers(api, make_user, listings):
    """A throttled response is still a response (AUDIT.md M5)."""
    user = make_user()
    listing = listings[0]
    for _ in range(ORDER_LIMIT_PER_MIN + 2):
        r = httpx.post(f"{api}/api/orders/", headers=user.api_headers,
                       json=_order_payload(listing), timeout=30)
        if r.status_code == 429:
            assert r.headers.get("x-content-type-options") == "nosniff"
            assert r.headers.get("content-security-policy")
            return
    pytest.fail("never hit the limit")


# ── Blast radius ─────────────────────────────────────────────────────────────

def test_limit_is_per_caller_not_global(api, make_user, listings):
    """One user exhausting their budget must not lock everyone else out."""
    noisy = make_user()
    quiet = make_user()
    listing = listings[0]

    for _ in range(ORDER_LIMIT_PER_MIN + 2):
        httpx.post(f"{api}/api/orders/", headers=noisy.api_headers,
                   json=_order_payload(listing), timeout=30)

    r = httpx.post(f"{api}/api/orders/", headers=quiet.api_headers,
                   json=_order_payload(listing), timeout=30)
    assert r.status_code == 201, (
        f"a second user was throttled by the first's usage (HTTP {r.status_code}) -- "
        "the limit is global, not per caller"
    )


def test_reads_survive_an_exhausted_write_budget(api, make_user, listings):
    """Throttling writes must not take order history down with it."""
    user = make_user()
    listing = listings[0]
    for _ in range(ORDER_LIMIT_PER_MIN + 2):
        httpx.post(f"{api}/api/orders/", headers=user.api_headers,
                   json=_order_payload(listing), timeout=30)

    assert httpx.get(f"{api}/api/orders/", headers=user.api_headers, timeout=30).status_code == 200
    assert httpx.get(f"{api}/api/listings/", timeout=30).status_code == 200


def test_public_catalogue_is_not_throttled_by_normal_browsing(api):
    """A handful of ordinary reads must never trip a limit."""
    codes = [httpx.get(f"{api}/api/listings/", timeout=30).status_code for _ in range(15)]
    assert set(codes) == {200}, f"ordinary browsing got throttled: {codes}"
