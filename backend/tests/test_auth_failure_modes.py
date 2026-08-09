"""A failed verification and an impossible one must not look the same.

services/auth.py used to catch every exception from get_user() and answer 401.
That told clients to re-authenticate when the real problem was that Supabase could
not be reached -- advice that cannot work -- and made an outage invisible, since it
presented as a wall of 401s rather than 5xx. The HTTP/2 corruption fixed in
services/supabase_client.py surfaced exactly this way: valid sessions came back 401.

The split is 401 for a verdict on the token, 503 for no verdict at all, 500 for a
bug here. The response body stays identical on every path so M3's oracle property
survives -- only the status distinguishes them.

These are pure unit tests: get_user is replaced, so nothing here touches the
network or needs the backend running.
"""
import httpx
import pytest
from fastapi import HTTPException
from supabase_auth.errors import (
    AuthApiError,
    AuthInvalidJwtError,
    AuthRetryableError,
    AuthSessionMissingError,
)

import services.auth as auth_module
from services.auth import (
    AUTH_FAILED_DETAIL,
    INVALID_TOKEN_DETAIL,
    NOT_AUTHENTICATED_DETAIL,
    UNAVAILABLE_DETAIL,
    get_current_user,
)

HEADER = "Bearer sometoken"


@pytest.fixture
def raising(monkeypatch):
    """Make supabase.auth.get_user raise the given exception."""
    def _raising(exc):
        def _boom(*args, **kwargs):
            raise exc
        monkeypatch.setattr(auth_module.supabase.auth, "get_user", _boom)
    return _raising


def _call():
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(authorization=HEADER)
    return excinfo.value


# ── A verdict on the token: 401 ──────────────────────────────────────────────

@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_auth_api_error_4xx_is_401(raising, status):
    """Supabase answered and the answer was no. That is the caller's problem."""
    raising(AuthApiError("bad token", status, None))
    assert _call().status_code == 401


@pytest.mark.parametrize("exc", [
    AuthInvalidJwtError("malformed"),
    AuthSessionMissingError(),
])
def test_other_auth_errors_are_401(raising, exc):
    """Invalid-JWT and missing-session are verdicts too, not transport failures."""
    raising(exc)
    assert _call().status_code == 401


# ── No verdict available: 503 ────────────────────────────────────────────────

@pytest.mark.parametrize("exc", [
    httpx.ConnectError("connection refused"),
    httpx.ReadTimeout("timed out"),
    httpx.ConnectTimeout("timed out connecting"),
    httpx.PoolTimeout("pool exhausted"),
    httpx.RemoteProtocolError("server disconnected"),
])
def test_transport_errors_are_503(raising, exc):
    """gotrue only converts HTTPStatusError and RuntimeError, so these arrive raw.

    RemoteProtocolError stays here on purpose: the peer spoke badly or the
    connection died, and this process cannot be sure it caused that. h2's
    ConnectionTerminated arrives this way.
    """
    raising(exc)
    assert _call().status_code == 503


@pytest.mark.parametrize("status", [0, 502, 503, 504, 520, 524, 530])
def test_retryable_errors_are_503(raising, status):
    """supabase_auth's own upstream-is-unwell class, including its status-0 path."""
    raising(AuthRetryableError("upstream unwell", status))
    assert _call().status_code == 503


@pytest.mark.parametrize("status", [500, 502, 599])
def test_auth_api_error_5xx_is_503(raising, status):
    """An outage wearing an auth exception.

    500 is the one that matters: it is absent from supabase_auth's retryable list,
    so it arrives as AuthApiError and is only classified correctly by the explicit
    status check in get_current_user.
    """
    raising(AuthApiError("upstream failed", status, None))
    assert _call().status_code == 503


def test_503_carries_retry_after(raising):
    """A 401 tells a client to re-authenticate; only this tells it to wait."""
    raising(httpx.ConnectError("connection refused"))
    exc = _call()
    assert exc.headers and exc.headers.get("Retry-After"), (
        "503 without Retry-After leaves clients guessing"
    )


# ── A bug here: 500 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "Illegal header value b'abc\\n'",     # a credential carrying whitespace
    "Stream ID 3 is lower than the last",  # h2 corruption, via httpcore's mapping
])
def test_local_protocol_errors_are_500_not_503(raising, message):
    """A request we built badly is our defect, not an outage.

    LocalProtocolError is an httpx.HTTPError, so it would otherwise match the
    transport branch and answer 503 with Retry-After -- telling clients to retry
    something that will never fix itself, and pointing dashboards at Supabase for
    a bug on this side. Both faults seen in practice arrived this way: a
    whitespace-tainted credential, and h2 stream-state corruption from sharing one
    HTTP/2 connection across threads.
    """
    raising(httpx.LocalProtocolError(message))
    failure = _call()
    assert failure.status_code == 500
    assert failure.detail == AUTH_FAILED_DETAIL


def test_local_protocol_error_carries_no_retry_after(raising):
    """Retry-After on a permanent defect is an instruction to loop forever."""
    raising(httpx.LocalProtocolError("Illegal header value"))
    assert not (_call().headers or {}).get("Retry-After")


def test_unexpected_exception_is_500(raising):
    """Not a judgement on the caller. Still fails closed -- no user is returned."""
    raising(ValueError("something we did not anticipate"))
    bug = _call()
    assert bug.status_code == 500
    assert bug.detail == AUTH_FAILED_DETAIL


def test_the_three_details_are_all_distinct():
    """Each status says something different, so each body must too.

    Reusing one string across them is what made an outage read as a bad token.
    """
    details = {INVALID_TOKEN_DETAIL, UNAVAILABLE_DETAIL, AUTH_FAILED_DETAIL}
    assert len(details) == 3, f"detail strings collapsed into {details}"


def test_a_returned_none_user_is_still_401(monkeypatch):
    """No exception, but no user either: a verdict, not an outage."""
    monkeypatch.setattr(auth_module.supabase.auth, "get_user", lambda *a, **k: None)
    assert _call().status_code == 401


# ── M3: the body must not become an oracle ───────────────────────────────────

@pytest.mark.parametrize("exc", [
    AuthApiError("token expired at 12:03 for user abc123", 401, None),
    AuthApiError("signature verification failed for key kid-7", 403, None),
    AuthInvalidJwtError("malformed segment 2"),
    AuthSessionMissingError(),
])
def test_every_401_returns_one_fixed_detail(raising, exc):
    """Which property of a token was wrong is exactly what M3 conceals.

    All four of these are different rejection reasons and must be indistinguishable
    to the caller, so they share one string regardless of what the exception said.
    """
    raising(exc)
    rejection = _call()
    assert rejection.status_code == 401
    assert rejection.detail == INVALID_TOKEN_DETAIL


@pytest.mark.parametrize("exc", [
    AuthApiError("upstream failed", 500, None),
    AuthRetryableError("gateway timeout talking to db-1.internal", 504),
    httpx.ConnectError("failed to connect to db-1.internal:5432"),
])
def test_every_503_returns_its_own_detail(raising, exc):
    """A distinct message from the 401s, and identical across every outage cause.

    This partitions no set of tokens -- a valid one gets it too -- so it answers
    no question an attacker can ask, while telling an operator the truth.
    """
    raising(exc)
    outage = _call()
    assert outage.status_code == 503
    assert outage.detail == UNAVAILABLE_DETAIL


def test_the_two_details_are_actually_different():
    """The whole point of the split. Collapsing them would pass every test above."""
    assert UNAVAILABLE_DETAIL != INVALID_TOKEN_DETAIL


@pytest.mark.parametrize("exc", [
    AuthApiError("token expired at 12:03 for user abc123", 401, None),
    AuthRetryableError("gateway timeout talking to db-1.internal", 504),
    httpx.ConnectError("failed to connect to db-1.internal:5432"),
    ValueError("internal detail that must not escape"),
])
def test_no_failure_leaks_the_underlying_exception_text(raising, exc):
    """Hostnames, ports, key ids and timestamps stay server-side on every path."""
    raising(exc)
    detail = str(_call().detail)
    assert detail in (INVALID_TOKEN_DETAIL, UNAVAILABLE_DETAIL, AUTH_FAILED_DETAIL), (
        f"unrecognised detail leaked to the client: {detail!r}"
    )
    for fragment in ("db-1.internal", "5432", "12:03", "abc123", "must not escape"):
        assert fragment not in detail


def test_missing_header_is_unchanged(monkeypatch):
    """The pre-existing no-credentials path must keep its own message and 401."""
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(authorization=None)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == NOT_AUTHENTICATED_DETAIL


def test_malformed_header_is_401(monkeypatch):
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(authorization="Basic abc123")
    assert excinfo.value.status_code == 401


# ── The happy path still works ───────────────────────────────────────────────

def test_valid_token_returns_the_user(monkeypatch):
    """Guards against the ladder above accidentally rejecting good tokens."""
    class _User:
        id = "user-123"

    class _Response:
        user = _User()

    monkeypatch.setattr(auth_module.supabase.auth, "get_user", lambda *a, **k: _Response())
    assert get_current_user(authorization=HEADER).id == "user-123"
