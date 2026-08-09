"""Step 4 — CORS must name the origins it trusts (AUDIT.md finding M1).

The deployed config was allow_origins=["*"] with allow_methods=["*"] and
allow_headers=["*"], measured live: any origin on the internet could call the API
with an Authorization header.

allow_credentials was False, which does block the classic drive-by CSRF, so this
was never the finding that got you owned -- it is the defence-in-depth layer that
should have blunted H3 (tokens in localStorage) and did not.

The replacement must still admit the local dev server and this project's own
Vercel preview deployments, which is what the wildcard was reaching for.
"""
import os

import httpx
import pytest


# Every test here drives the running backend and a live Supabase project.
pytestmark = pytest.mark.integration

# The project slug is configuration, not a constant -- it moved out of main.py so
# that deploying this elsewhere does not mean editing source. The tests read the
# same variable the app does, and skip the preview cases when it is not set.
SLUG = os.getenv("VERCEL_PROJECT_SLUG", "").strip()

requires_slug = pytest.mark.skipif(
    not SLUG,
    reason="VERCEL_PROJECT_SLUG not configured; no preview origins to test",
)

# Preview URLs Vercel generates for whichever project is configured.
VERCEL_PREVIEWS = [
    f"https://{SLUG}.vercel.app",                    # production
    f"https://{SLUG}-git-main-mahrous.vercel.app",   # branch deploy
    f"https://{SLUG}-abc123xyz.vercel.app",          # commit deploy
]

# Smuggling variants are built from the same slug, so they stay meaningful.
FOREIGN_ORIGINS = [
    "https://evil.example.com",
    f"https://{SLUG}.vercel.app.evil.com",   # suffix smuggling
    f"https://evil-{SLUG}.vercel.app",       # prefix smuggling
    "https://someone-elses-app.vercel.app",  # different Vercel project
    f"http://{SLUG}.vercel.app",             # downgraded to http
]


def _acao(api, origin):
    """Access-Control-Allow-Origin returned for a simple GET from `origin`."""
    r = httpx.get(f"{api}/api/listings/", headers={"Origin": origin}, timeout=30)
    return r.headers.get("access-control-allow-origin")


def _preflight(api, origin, method="POST"):
    return httpx.options(
        f"{api}/api/orders/",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
        timeout=30,
    )


def test_wildcard_origin_is_gone(api):
    """The headline of M1: no response may hand back '*'."""
    assert _acao(api, "https://evil.example.com") != "*", (
        "API still answers every origin with Access-Control-Allow-Origin: *"
    )


def test_local_dev_origin_is_allowed(api):
    """FRONTEND_URL must keep working or local development breaks."""
    origin = "http://localhost:5173"
    assert _acao(api, origin) == origin, (
        f"local dev origin {origin} was not allowed; the frontend cannot call the API"
    )


@requires_slug
@pytest.mark.parametrize("origin", VERCEL_PREVIEWS)
def test_own_vercel_previews_are_allowed(api, origin):
    """The legitimate need the wildcard was papering over."""
    assert _acao(api, origin) == origin, f"own Vercel deployment {origin} was blocked"


@pytest.mark.parametrize("origin", FOREIGN_ORIGINS)
def test_foreign_origins_are_refused(api, origin):
    """Anything that is not ours must get no CORS grant at all."""
    got = _acao(api, origin)
    assert got != origin and got != "*", (
        f"foreign origin {origin} was granted CORS access (got {got!r}). "
        "Prefix/suffix smuggling around the preview regex is the usual cause."
    )


def test_preflight_from_own_origin_succeeds(api):
    r = _preflight(api, "http://localhost:5173")
    assert r.status_code < 400, f"preflight from the dev origin failed: HTTP {r.status_code}"
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_preflight_from_foreign_origin_is_refused(api):
    r = _preflight(api, "https://evil.example.com")
    granted = r.headers.get("access-control-allow-origin")
    assert granted not in ("*", "https://evil.example.com"), (
        f"preflight granted a foreign origin: {granted!r}"
    )


def test_public_endpoint_still_serves_non_browser_clients(api):
    """CORS is a browser control; curl and the tests must be unaffected."""
    r = httpx.get(f"{api}/api/listings/", timeout=30)
    assert r.status_code == 200, "locking down CORS must not break non-browser callers"
