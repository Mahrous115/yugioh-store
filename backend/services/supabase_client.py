"""Singleton Supabase client using the service-role key.

The service key bypasses Row Level Security, so this client is only used
server-side in the FastAPI app — never exposed to the browser.
"""
import os

import httpx
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def _clean(name: str, raw: str) -> str:
    """Strip surrounding whitespace, and refuse anything left inside.

    A credential that picks up whitespace is not rejected by anything until it is
    encoded into an HTTP header, at which point httpx raises LocalProtocolError
    ("Illegal header value") on every request -- client-side, so nothing is sent
    and nothing appears in any Supabase log. The app looks healthy and fails at
    request time instead of startup. A single trailing space is enough.

    The strip and the check are doing different jobs, and the check is the one
    that matters. Stripping fixes a value with whitespace around it. A paste that
    wrapped across lines puts newlines in the MIDDLE, where strip() removes
    nothing at all and the value stays illegal -- so stripping alone would look
    like protection while leaving the original failure intact. Do not delete the
    interior check as redundant.

    Deliberately no format validation: no sb_secret_ prefix check, no length
    check. Supabase has changed key formats before and a validator encoding
    today's shape becomes a false rejection the day they change it again.
    Whitespace is safe to reject because it is invalid in an HTTP header value --
    a property of HTTP, not of Supabase.

    Nor is any attempt made to repair interior whitespace by removing it: a key
    with a newline through it might be a wrapped paste, two keys concatenated, or
    a truncation, and silently splicing it could authenticate as something
    unintended.

    Empty is not checked here on purpose -- create_client already raises
    "supabase_url is required" / "supabase_key is required" at import, and a
    whitespace-only value reaches that guard as empty once stripped.
    """
    value = raw.strip()
    if any(character.isspace() for character in value):
        # The value is never included: startup errors get pasted into issues.
        raise RuntimeError(
            f"{name} contains whitespace inside its value, which is almost always "
            "a paste that wrapped across lines. Re-copy it as a single line. The "
            "value is not shown here on purpose."
        )
    return value


# Read and validated at import so a malformed credential is a startup failure --
# on Container Apps, a crash-looping revision naming the variable, which
# ENV_VARS.md already teaches you to read. The alternative is a revision that
# goes healthy and then answers every request with an error.
_url: str = _clean("SUPABASE_URL", os.environ["SUPABASE_URL"])
_key: str = _clean("SUPABASE_SERVICE_KEY", os.environ["SUPABASE_SERVICE_KEY"])

supabase: Client = create_client(_url, _key)


# ── HTTP/1.1 only ────────────────────────────────────────────────────────────
#
# This module-level client is shared by every request, and the route handlers are
# `def` rather than `async def`, so FastAPI runs them in a threadpool -- several
# threads use these sessions at once.
#
# httpx.Client is documented thread-safe, and httpcore's sync HTTP/1.1 pool is
# safe under that sharing. Its sync HTTP/2 implementation is not: the per-
# connection stream state is mutated without synchronisation, so concurrent
# threads multiplexing over one h2 connection corrupt it. Observed under a
# four-way concurrent burst: StreamIDTooLowError, KeyError on del
# self._events[stream_id], ConnectionTerminated, and "Received pseudo-header in
# trailer". The damage is not confined to the racing request -- the connection is
# shared, so it also broke token verification, and valid sessions came back 401.
#
# supabase-py hardcodes http2=True when it builds these sessions and exposes no
# option to turn it off (postgrest/_sync/client.py:104 and
# supabase_auth/_sync/gotrue_base_api.py:29, as pinned: supabase==2.31.0,
# postgrest==2.31.0, supabase-auth==2.31.0). So the sessions are built normally
# and then replaced with HTTP/1.1 equivalents, which keeps the base URL, headers
# and timeouts the library configured rather than guessing at them.
#
# Losing multiplexing costs a connection per concurrent call instead of shared
# streams; at this service's traffic that is not measurable. The proper fix is
# async handlers with AsyncClient, where no client crosses a thread boundary.
#
# Only postgrest and auth are treated. .storage and .functions carry the same
# hardcoded http2=True (storage3/_sync/client.py:82 and
# supabase_functions/_sync/functions_client.py:75) but are lazy properties this
# app never accesses, so those sessions are never built and there is nothing live
# to fix. Forcing them into existence purely to replace them would add two unused
# connection pools and two more reach-ins whose correctness nothing can exercise.
#
# ADDING IMAGE UPLOADS MEANS EXTENDING THIS. supabase.storage.session needs the
# same swap, and it should not simply reuse _without_http2's copied timeout:
# uploads are large-body and long-lived, which is why storage_client_timeout is a
# separate ClientOptions field. Pick that timeout deliberately when the feature
# lands. Untreated, concurrent uploads reproduce the failure this fixes --
# StreamIDTooLowError and RemoteProtocolError under load.
# tests/test_supabase_transport.py asserts these stay unbuilt, so the day someone
# uses storage or functions that test fails and points back here.
#
# Note also that _listen_to_auth_events resets ._postgrest to None on SIGNED_IN /
# TOKEN_REFRESHED / SIGNED_OUT, which would rebuild it with HTTP/2. That cannot
# fire here -- this client only ever uses the service key and never signs in --
# but it is why the regression test asserts on the live sessions.

def _without_http2(client: httpx.Client) -> httpx.Client:
    """An equivalent client that speaks HTTP/1.1 only. Closes the one it replaces.

    verify and proxy are not readable back off a constructed client, so the
    replacement takes the httpx defaults (verify on, no proxy) -- which is what
    create_client used above, since nothing overrides them here.
    """
    replacement = httpx.Client(
        base_url=client.base_url,
        headers=client.headers,
        timeout=client.timeout,
        follow_redirects=client.follow_redirects,
        http2=False,
    )
    client.close()  # otherwise the discarded h2 pool keeps its connections
    return replacement


supabase.postgrest.session = _without_http2(supabase.postgrest.session)
supabase.auth._http_client = _without_http2(supabase.auth._http_client)
