"""Step 7 — every response carries baseline security headers (AUDIT.md M5).

Measured on the audited build: zero of Strict-Transport-Security, X-Frame-Options,
X-Content-Type-Options and Content-Security-Policy were present. The only headers set
were Cache-Control/Pragma, left over from working around Railway's CDN.

The CSP matters most here: it is the mitigation that would contain H3 (tokens in
localStorage, stealable by any XSS). This service returns JSON, so it can afford the
strictest possible policy -- default-src 'none' -- which the interactive docs cannot,
hence the separate case below.
"""
import importlib

import httpx
import pytest
from fastapi.testclient import TestClient

EXPECTED = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}

# Paths covering success, auth failure and not-found -- headers must not depend on
# the happy path being taken.
PATHS = ["/", "/api/listings/", "/api/orders/", "/no-such-route"]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("header,value", sorted(EXPECTED.items()))
def test_header_present_on_every_response(api, path, header, value):
    r = httpx.get(f"{api}{path}", timeout=30)
    assert r.headers.get(header) == value, (
        f"{path} (HTTP {r.status_code}) missing {header}: {value!r}, "
        f"got {r.headers.get(header)!r}"
    )


@pytest.mark.parametrize("path", PATHS)
def test_csp_is_present_and_locked_down(api, path):
    r = httpx.get(f"{api}{path}", timeout=30)
    csp = r.headers.get("content-security-policy")
    assert csp, f"{path} has no Content-Security-Policy"
    assert "default-src 'none'" in csp, (
        f"{path} CSP is not deny-by-default: {csp!r}. A JSON API can afford the "
        "strictest policy there is."
    )
    assert "frame-ancestors 'none'" in csp, f"{path} CSP allows framing: {csp!r}"


@pytest.mark.parametrize("path", PATHS)
def test_hsts_present(api, path):
    r = httpx.get(f"{api}{path}", timeout=30)
    hsts = r.headers.get("strict-transport-security", "")
    assert "max-age=" in hsts, f"{path} missing Strict-Transport-Security: {hsts!r}"


def test_headers_survive_an_auth_failure(api):
    """A 401 is exactly when you do not want headers quietly dropped."""
    r = httpx.get(f"{api}/api/orders/", headers={"Authorization": "Bearer nope"}, timeout=30)
    assert r.status_code == 401
    for header, value in EXPECTED.items():
        assert r.headers.get(header) == value, f"401 response dropped {header}"
    assert r.headers.get("content-security-policy")


def test_existing_no_cache_behaviour_is_preserved(api):
    """The pre-existing headers must not be clobbered by the new middleware."""
    r = httpx.get(f"{api}/", timeout=30)
    assert r.headers.get("cache-control") == "no-store"
    assert r.headers.get("pragma") == "no-cache"


def test_cors_headers_still_work(api):
    """Middleware ordering must not break the M1 allowlist."""
    origin = "http://localhost:5173"
    r = httpx.get(f"{api}/api/listings/", headers={"Origin": origin}, timeout=30)
    assert r.headers.get("access-control-allow-origin") == origin


# ── The docs exception ───────────────────────────────────────────────────────

def test_docs_get_a_csp_that_lets_swagger_ui_render(monkeypatch):
    """default-src 'none' would leave /docs a blank page.

    Swagger UI is served from a CDN with inline styles, so the docs routes need a
    looser policy. Their CSP must still be present and must still forbid framing --
    it is a relaxation, not an exemption.
    """
    import main
    monkeypatch.setenv("ENABLE_DOCS", "true")
    app = importlib.reload(main).app

    with TestClient(app) as client:
        r = client.get("/docs")
        assert r.status_code == 200
        csp = r.headers.get("content-security-policy")
        assert csp, "/docs has no CSP at all"
        assert "default-src 'none'" not in csp, (
            "/docs still has the API's deny-all CSP; Swagger UI cannot render"
        )
        assert "frame-ancestors 'none'" in csp, f"/docs CSP allows framing: {csp!r}"
        assert r.headers.get("x-content-type-options") == "nosniff"


@pytest.fixture(autouse=True)
def _restore_main():
    yield
    import main
    importlib.reload(main)
