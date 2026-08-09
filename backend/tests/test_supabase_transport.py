"""The shared Supabase sessions must stay HTTP/1.1 (services/supabase_client.py).

The route handlers are sync, so FastAPI runs them in a threadpool and these
module-level sessions are used by several threads at once. httpcore's sync HTTP/2
stream-state handling is not safe under that sharing, and the resulting connection
corruption surfaced as 500s on concurrent orders and 401s on valid tokens.

supabase-py hardcodes http2=True and offers no switch, so the fix replaces the
sessions after construction. A dependency bump that changes those internals would
otherwise silently restore HTTP/2 and bring the race back, which is what these
guard against. test_l8_stock.py::test_concurrent_buyers_cannot_oversell is the
behavioural half of this; these are the cheap, deterministic half.
"""
import httpx
import pytest

from services.supabase_client import supabase


def _http2_enabled(client):
    """Read HTTP/2 support off the live connection pool.

    httpx exposes no public accessor for this, so it means reaching through the
    transport. If a future httpx or httpcore changes that layout, this raises
    AttributeError and the test fails loudly rather than skipping the check --
    a guard that silently stops guarding is worse than no guard.
    """
    return client._transport._pool._http2


SESSIONS = [
    ("postgrest", lambda: supabase.postgrest.session),
    ("auth", lambda: supabase.auth._http_client),
]


@pytest.mark.parametrize("name,get_session", SESSIONS, ids=[s[0] for s in SESSIONS])
def test_session_is_http1_only(name, get_session):
    assert _http2_enabled(get_session()) is False, (
        f"the {name} session negotiated HTTP/2 again; concurrent requests will "
        "corrupt its connection state (see services/supabase_client.py)"
    )


@pytest.mark.parametrize("name,get_session", SESSIONS, ids=[s[0] for s in SESSIONS])
def test_session_is_a_real_httpx_client(name, get_session):
    """Guards the replacement itself, not just the flag it sets."""
    assert isinstance(get_session(), httpx.Client)


def test_postgrest_session_kept_its_base_url_and_credentials():
    """Rebuilding the session must not drop what the library configured on it.

    Losing the base URL or the service-key headers would break every query, so
    this fails fast and locally rather than as a confusing 401 from PostgREST.
    """
    session = supabase.postgrest.session

    assert str(session.base_url), "postgrest session lost its base_url"
    assert "/rest/v1" in str(session.base_url), (
        f"postgrest base_url no longer points at the REST API: {session.base_url}"
    )

    lowered = {k.lower() for k in session.headers}
    assert "apikey" in lowered, "postgrest session lost its apikey header"
    assert "authorization" in lowered, "postgrest session lost its Authorization header"


def test_postgrest_session_kept_a_timeout():
    """A session with no timeout can hang a worker thread indefinitely."""
    timeout = supabase.postgrest.session.timeout

    assert timeout is not None
    assert timeout.read is not None, f"read timeout was dropped: {timeout}"


@pytest.mark.integration
def test_the_rebuilt_session_actually_works():
    """Attribute checks prove configuration, not function. This proves function.

    The only test in this file that leaves the process, so it is the only one
    marked. It stays here beside the attribute checks it backs up rather than
    moving to an integration file where the connection would be lost.
    """
    result = supabase.table("listings").select("card_id").limit(1).execute()

    assert result.data is not None, "the replaced postgrest session cannot query"


# ── The untreated clients ────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["storage", "functions"])
def test_untreated_clients_are_never_built(name):
    """storage and functions still construct with http2=True and are NOT swapped.

    That is safe only for as long as nothing touches them, so this asserts the
    premise rather than trusting it. The private attribute is read deliberately:
    the public property would construct the very client this is checking is
    absent.

    If this fails, someone started using storage or functions -- most likely image
    uploads. Extend _without_http2 to that session before going further, with a
    timeout chosen for large uploads rather than the copied default. See the
    comment in services/supabase_client.py.
    """
    assert getattr(supabase, f"_{name}") is None, (
        f"supabase.{name} has been built, and it negotiates HTTP/2 -- concurrent "
        f"use will corrupt its connection state exactly as postgrest's did"
    )
