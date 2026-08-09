"""Step 5 — auth failures must not narrate the backend's internals (AUDIT.md M3).

get_current_user ended its except block with

    raise HTTPException(status_code=401, detail=str(exc))

so whatever the auth library or the network raised went straight to an unauthenticated
caller. Measured live:

    {"detail":"[Errno 11001] getaddrinfo failed"}                     # DNS failure
    {"detail":"invalid JWT: ... could not JSON decode header: ..."}   # library internals

Individually minor; collectively a free oracle into the backend's dependencies and
state, available before authenticating.
"""
import httpx
import pytest


# Every test here drives the running backend and a live Supabase project.
pytestmark = pytest.mark.integration

# Substrings that should never reach a client. Drawn from responses actually observed
# on this backend, plus the usual shapes of leaked internals.
LEAK_MARKERS = [
    "errno",
    "getaddrinfo",
    "traceback",
    "supabase",
    "httpx",
    "postgrest",
    "unable to parse or verify signature",
    "could not json decode",
    "signature is invalid",
    "token is malformed",
    ".py",
]

BAD_TOKENS = [
    pytest.param("garbage.token.here", id="unparseable"),
    pytest.param(
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NSIsImV4cCI6OTk5OTk5OTk5OX0.aaaa",
        id="bad-signature",
    ),
    # Not "" -- "Bearer " has a trailing space, which httpx refuses to send as a
    # header value, so the empty-token path is unreachable from a conforming client.
    pytest.param(".", id="degenerate"),
    pytest.param("a" * 4000, id="oversized"),
]

PROTECTED = ["/api/orders/", "/api/wishlist/"]


@pytest.mark.parametrize("token", BAD_TOKENS)
@pytest.mark.parametrize("path", PROTECTED)
def test_rejection_does_not_leak_internals(api, path, token):
    r = httpx.get(f"{api}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 401, f"expected 401, got {r.status_code}"

    body = r.text.lower()
    leaked = [m for m in LEAK_MARKERS if m in body]
    assert not leaked, f"401 body leaked {leaked}: {r.text[:250]}"


@pytest.mark.parametrize("token", BAD_TOKENS)
def test_rejection_message_is_generic(api, token):
    """One stable message, so the response cannot be used to classify failures."""
    r = httpx.get(f"{api}/api/orders/", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.json().get("detail") == "Invalid or expired token", (
        f"expected a fixed generic message, got: {r.json().get('detail')!r}"
    )


def test_missing_header_is_still_distinguishable(api):
    """"You sent no credentials" is not a leak and is useful to clients."""
    r = httpx.get(f"{api}/api/orders/", timeout=30)
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"


def test_malformed_authorization_scheme_is_rejected(api):
    r = httpx.get(f"{api}/api/orders/", headers={"Authorization": "NotBearer xyz"}, timeout=30)
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"


def test_valid_token_still_authenticates(api, make_user):
    """The fix must not turn real sessions away."""
    user = make_user()
    r = httpx.get(f"{api}/api/orders/", headers=user.api_headers, timeout=30)
    assert r.status_code == 200, f"valid token rejected: HTTP {r.status_code} {r.text[:200]}"


def test_admin_denial_does_not_leak_either(api, make_user):
    """get_admin_user has its own except block; same rule applies."""
    user = make_user()
    r = httpx.post(
        f"{api}/api/listings/",
        headers=user.api_headers,
        json={
            "card_id": 99999996,
            "card_name": "PYTEST-DENIED",
            "card_image": "https://example.invalid/x.jpg",
            "price": 1.0,
            "stock": 1,
        },
        timeout=30,
    )
    assert r.status_code == 403
    body = r.text.lower()
    leaked = [m for m in LEAK_MARKERS if m in body]
    assert not leaked, f"403 body leaked {leaked}: {r.text[:250]}"
