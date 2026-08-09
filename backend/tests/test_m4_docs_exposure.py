"""Step 6 — the API must not publish its own schema by default (AUDIT.md M4).

/docs, /redoc and /openapi.json all returned 200 to anonymous callers, handing over a
complete machine-readable map of every endpoint, parameter and model. Not a
vulnerability on its own; a reconnaissance accelerator, and there is no reason for it
to be reachable in production.

Closed by default, opened only when ENABLE_DOCS is explicitly set.
"""
import importlib

import httpx
import pytest
from fastapi.testclient import TestClient

DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


# ── Default posture, against the running server ──────────────────────────────

@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_are_closed_by_default(api, path):
    r = httpx.get(f"{api}{path}", timeout=30)
    assert r.status_code == 404, (
        f"{path} is reachable (HTTP {r.status_code}); the full API surface is public"
    )


def test_the_api_itself_still_works_with_docs_off(api):
    """Disabling docs must not disable anything real."""
    r = httpx.get(f"{api}/api/listings/", timeout=30)
    assert r.status_code == 200
    assert httpx.get(f"{api}/", timeout=30).status_code == 200


# ── The toggle, in-process ───────────────────────────────────────────────────
#
# main.py reads the flag at import time, so the enabled case is exercised by
# reloading the module under a patched environment rather than restarting uvicorn.

def _app_with_env(monkeypatch, value):
    """Re-import main with ENABLE_DOCS forced to `value` (None means unset).

    load_dotenv is stubbed out for the reload. Without it, re-importing main
    re-reads backend/.env and puts back the very variable the test just deleted,
    so the unset case would silently test the developer's local config instead.
    The setenv cases were never affected -- load_dotenv does not override a
    variable that is already set, and only the delenv path leaves a gap for it
    to fill.
    """
    import main
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    if value is None:
        monkeypatch.delenv("ENABLE_DOCS", raising=False)
    else:
        monkeypatch.setenv("ENABLE_DOCS", value)
    return importlib.reload(main).app


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_can_be_enabled_explicitly(monkeypatch, path):
    with TestClient(_app_with_env(monkeypatch, "true")) as client:
        assert client.get(path).status_code == 200, f"{path} did not open with ENABLE_DOCS=true"


@pytest.mark.parametrize("value", ["", "false", "0", "no"])
@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_stay_closed_for_falsey_values(monkeypatch, path, value):
    """Anything other than an explicit opt-in must leave them shut."""
    with TestClient(_app_with_env(monkeypatch, value)) as client:
        assert client.get(path).status_code == 404, (
            f"{path} opened with ENABLE_DOCS={value!r}; only an explicit yes should open it"
        )


def test_unset_env_defaults_to_closed(monkeypatch):
    with TestClient(_app_with_env(monkeypatch, None)) as client:
        for path in DOC_PATHS:
            assert client.get(path).status_code == 404, f"{path} open when ENABLE_DOCS is unset"


@pytest.fixture(autouse=True)
def _restore_main():
    """Leave the imported module matching the real environment for other tests."""
    yield
    import main
    importlib.reload(main)
