"""Sentinel translation on the order path: no leakage, no confusable card names.

`public.place_order` reports every failure as a RAISE EXCEPTION string, and
`_translate_place_order_error` turns those back into status codes. Two defects lived
in that translation:

  M3   The handler fell back to `str(exc)` when the exception carried no `.message`.
       That string is a repr of the whole postgrest error dict, and the
       INSUFFICIENT_STOCK pattern's trailing `(.*)` group -- unanchored, greedy, and
       under re.DOTALL -- captured the card name *plus* the surrounding
       "', 'code': 'P0001', ...}" straight into the 409 detail sent to the client.
       AUDIT.md M3 forbids the endpoint leaking exception text.

  --   All five patterns used re.search, so a sentinel was recognised anywhere in the
       message, and they were tried in a fixed order with NOT_LISTED first.
       INSUFFICIENT_STOCK carries `card_name` as its last field precisely because
       names are free text, so a card called "Foo NOT_LISTED:9" turned its own 409
       into a 400. Card names are admin-controlled today; multi-seller listings would
       make them seller-controlled.

Unlike the rest of backend/tests/, nothing in this file touches Supabase or a running
backend. The RPC is stubbed and the auth dependency overridden, so it runs offline.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import main
from routers import orders
from services.auth import get_current_user

# Names chosen to be hostile in exactly the ways the SQL format string allows: a
# colon (the field delimiter), an embedded sentinel, and a newline.
PLAIN_NAME = "Dark Magician"
COLON_NAME = "Elemental HERO Neos: Blaze"
SENTINEL_NAME = "Foo NOT_LISTED:9"
NEWLINE_NAME = "Cyber-Stein\nLimited Edition"

FLAT_500_DETAIL = "Could not place order."

# Substrings that only ever appear in a postgrest error repr, never in a message this
# API is willing to say out loud.
LEAK_MARKERS = ["P0001", "code", "hint", "details", "{", "}", "'"]


def _error_dict_repr(message):
    """What str(exc) yields when the exception is the whole postgrest error dict."""
    return repr({"message": message, "code": "P0001", "hint": None, "details": None})


class PostgrestLikeError(Exception):
    """A postgrest APIError as the handler is entitled to see it.

    The verbatim RAISE text on `.message`; the dict repr on str(), so a test that
    passes for the wrong reason -- reading the repr rather than the message -- still
    trips the leak assertions.
    """

    def __init__(self, message):
        self.message = message
        super().__init__(_error_dict_repr(message))


class NoMessageError(Exception):
    """A postgrest error that does NOT expose `.message`.

    Exceptions have no `.message` attribute in Python 3, so this is simply what any
    other failure out of the RPC call looks like. str() is then the error dict repr,
    which is the string the old code fell back to parsing.
    """

    def __init__(self, message):
        super().__init__(_error_dict_repr(message))


class StubUser:
    """Stands in for the Supabase user object; only `.id` is ever read."""

    id = "00000000-0000-0000-0000-0000000000ab"


@pytest.fixture
def place_order(monkeypatch):
    """POST a one-line order whose place_order RPC raises `exc`; return the response."""

    def _post(exc):
        class _Rpc:
            def execute(self):
                raise exc

        class _Supabase:
            def rpc(self, fn, params):
                assert fn == "place_order", f"handler called an unexpected RPC: {fn}"
                return _Rpc()

        # orders.py does `from services.supabase_client import supabase`, so the name
        # to replace is the one bound in the router module, not the one in services.
        monkeypatch.setattr(orders, "supabase", _Supabase())
        main.app.dependency_overrides[get_current_user] = StubUser

        try:
            with TestClient(main.app) as client:
                return client.post(
                    "/api/orders/",
                    # The override means this token is never verified, but the rate
                    # limiter buckets on the raw header (services/rate_limit.py). A
                    # fresh one per call keeps these tests out of each other's
                    # 5-per-minute budget.
                    headers={"Authorization": f"Bearer {uuid.uuid4().hex}"},
                    json={"items": [{"card_id": 1, "quantity": 3}]},
                )
        finally:
            main.app.dependency_overrides.pop(get_current_user, None)

    return _post


def _detail(response):
    return response.json()["detail"]


# ── M3: the fallback path must not leak the exception repr ───────────────────

def test_error_without_a_message_attribute_does_not_leak_the_repr(place_order):
    """The M3 defect itself: no `.message`, so the old code parsed str(exc).

    An exception that does not carry the RAISE text verbatim is not a recognised
    place_order sentinel, whatever its repr happens to contain, and must be handled
    as an unknown server-side failure.
    """
    response = place_order(NoMessageError(f"INSUFFICIENT_STOCK:2:5:{PLAIN_NAME}"))
    detail = _detail(response)

    leaked = [marker for marker in LEAK_MARKERS if marker in detail]
    assert not leaked, f"error detail leaked {leaked} from the exception repr: {detail!r}"

    assert response.status_code == 500, (
        f"expected a flat 500 for an exception with no .message, "
        f"got HTTP {response.status_code}: {detail!r}"
    )
    assert detail == FLAT_500_DETAIL


def test_postgrest_api_error_still_exposes_message():
    """Guards the cost of the fix above: it assumes APIError carries `.message`.

    If a postgrest upgrade stops exposing it, every sentinel silently degrades to a
    flat 500 -- out-of-stock stops being a 409, a stale price stops being a 400. That
    should fail here, at the dependency bump, rather than in production. Constructed
    directly, so this makes no network call.
    """
    from postgrest.exceptions import APIError

    sentinel = f"INSUFFICIENT_STOCK:1:3:{PLAIN_NAME}"
    exc = APIError({"message": sentinel, "code": "P0001", "hint": None, "details": None})

    assert getattr(exc, "message", None) == sentinel, (
        "postgrest no longer exposes the RAISE text on APIError.message; "
        "_translate_place_order_error can no longer recognise any sentinel."
    )


# ── Anchoring: card names are free text and must not steer the status code ───

def test_card_name_containing_a_colon_survives_intact(place_order):
    """`card_name` is last in the SQL format string so it may contain the delimiter."""
    response = place_order(PostgrestLikeError(f"INSUFFICIENT_STOCK:1:3:{COLON_NAME}"))

    assert response.status_code == 409
    detail = _detail(response)
    assert f'"{COLON_NAME}"' in detail, (
        f"card name was truncated at the colon: {detail!r}"
    )
    assert "3 requested, 1 available" in detail, f"stock figures misparsed: {detail!r}"


def test_card_name_containing_another_sentinel_is_still_a_conflict(place_order):
    """A name carrying NOT_LISTED must not turn its own 409 into a 400.

    Not exploitable while names are admin-controlled. It stops being admin-controlled
    the moment listings are multi-seller.
    """
    response = place_order(PostgrestLikeError(f"INSUFFICIENT_STOCK:1:3:{SENTINEL_NAME}"))

    assert response.status_code == 409, (
        f'a card named "{SENTINEL_NAME}" reported HTTP {response.status_code} '
        f"instead of 409: {_detail(response)!r}"
    )
    assert f'"{SENTINEL_NAME}"' in _detail(response)


def test_card_name_containing_a_newline_survives(place_order):
    """re.DOTALL is load-bearing, and `$` would silently eat a trailing newline."""
    response = place_order(PostgrestLikeError(f"INSUFFICIENT_STOCK:1:3:{NEWLINE_NAME}"))

    assert response.status_code == 409
    assert NEWLINE_NAME in _detail(response), (
        f"card name did not survive the newline: {_detail(response)!r}"
    )


# ── Anything unrecognised stays a flat 500 ───────────────────────────────────

def test_an_unrecognised_database_error_is_a_flat_500(place_order):
    """No sentinel at all: the text is for the log, never for the client."""
    response = place_order(PostgrestLikeError("connection to server was lost"))

    assert response.status_code == 500
    assert _detail(response) == FLAT_500_DETAIL
    assert "connection" not in _detail(response)
