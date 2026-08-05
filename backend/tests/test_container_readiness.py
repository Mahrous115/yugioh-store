"""Container-readiness behaviour: health probe, env-driven CORS, stdout logging.

These cover the Phase 2 changes made ahead of containerising for Azure Container
Apps. The theme is that deployment config must be changeable on a running revision
rather than baked into the image, and that the platform's probe must not depend on
a third party being up.
"""
import importlib
import logging
import os
import re
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient


# ── /health ──────────────────────────────────────────────────────────────────

def test_health_returns_200(api):
    r = httpx.get(f"{api}/health", timeout=30)
    assert r.status_code == 200, f"health probe failed: HTTP {r.status_code}"
    assert r.json()["status"] == "ok"


def test_root_still_healthy(api):
    """/ predates /health and existing callers still use it."""
    r = httpx.get(f"{api}/", timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_does_not_touch_the_database(monkeypatch):
    """A probe that queries Supabase turns their outage into our outage.

    The platform would kill and restart healthy replicas because a third party is
    down. Proven by making any use of the Supabase client explode, then probing.
    """
    import main
    import services.supabase_client as sc

    class Exploding:
        def __getattr__(self, name):
            raise AssertionError(
                f"/health touched the Supabase client (accessed .{name})"
            )

    monkeypatch.setattr(sc, "supabase", Exploding())

    with TestClient(main.app) as client:
        r = client.get("/health")

    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_endpoints_are_exempt_from_rate_limiting():
    """A probe hits a fixed path every few seconds — exactly what the limiter
    rejects. A throttled 429 would read to the platform as an unhealthy container."""
    from services.rate_limit import limiter

    exempt = limiter._exempt_routes
    assert "main.health" in exempt, "/health is not exempt from rate limiting"
    assert "main.health_check" in exempt, "/ is not exempt from rate limiting"


# ── CORS is configuration, not source ────────────────────────────────────────

def _reload_main(monkeypatch, **env):
    """Re-import main with a patched environment. Config is read at import.

    load_dotenv is stubbed out for the reload. Without it, re-importing main
    re-reads backend/.env and puts back the very variables the test just deleted,
    so "unset" cases would silently test the developer's local config instead.
    """
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    for key in ("CORS_ALLOWED_ORIGINS", "FRONTEND_URL",
                "VERCEL_PROJECT_SLUG", "CORS_PREVIEW_ORIGIN_REGEX"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import main
    return importlib.reload(main)


@pytest.fixture(autouse=True)
def _restore_main():
    """Leave the imported module matching the real environment for other tests."""
    yield
    import main
    importlib.reload(main)


def test_localhost_dev_origin_always_allowed(monkeypatch):
    """Leaving it out is the commonest way to break local work by accident."""
    m = _reload_main(monkeypatch)
    assert "http://localhost:5173" in m.ALLOWED_ORIGINS


def test_origins_come_from_env_comma_separated(monkeypatch):
    """Adding an Azure origin must not require rebuilding the image."""
    m = _reload_main(
        monkeypatch,
        CORS_ALLOWED_ORIGINS="https://a.azurecontainerapps.io, https://b.example.com",
    )
    assert "https://a.azurecontainerapps.io" in m.ALLOWED_ORIGINS
    assert "https://b.example.com" in m.ALLOWED_ORIGINS
    assert "http://localhost:5173" in m.ALLOWED_ORIGINS


def test_trailing_slashes_are_normalised(monkeypatch):
    """Browsers never send a trailing slash in Origin, so a configured one would
    silently never match."""
    m = _reload_main(monkeypatch, CORS_ALLOWED_ORIGINS="https://a.example.com/")
    assert "https://a.example.com" in m.ALLOWED_ORIGINS


def test_legacy_frontend_url_still_honoured(monkeypatch):
    """It is set in existing .env files and documented in the README; ignoring it
    would present as 'CORS is broken' with no clue why."""
    m = _reload_main(monkeypatch, FRONTEND_URL="https://legacy.example.com")
    assert "https://legacy.example.com" in m.ALLOWED_ORIGINS


def test_both_origin_variables_merge(monkeypatch):
    m = _reload_main(
        monkeypatch,
        CORS_ALLOWED_ORIGINS="https://new.example.com",
        FRONTEND_URL="https://old.example.com",
    )
    assert "https://new.example.com" in m.ALLOWED_ORIGINS
    assert "https://old.example.com" in m.ALLOWED_ORIGINS


def test_no_preview_regex_without_configuration(monkeypatch):
    """The slug used to be hardcoded to one project. Unset must mean 'none'."""
    m = _reload_main(monkeypatch)
    assert m.PREVIEW_ORIGIN_REGEX is None


def test_slug_builds_an_anchored_https_only_pattern(monkeypatch):
    m = _reload_main(monkeypatch, VERCEL_PROJECT_SLUG="my-app")
    pattern = m.PREVIEW_ORIGIN_REGEX
    assert pattern and re.fullmatch(pattern, "https://my-app.vercel.app")
    assert re.fullmatch(pattern, "https://my-app-abc123.vercel.app")
    # the smuggling shapes must still not match
    assert not re.fullmatch(pattern, "http://my-app.vercel.app")
    assert not re.fullmatch(pattern, "https://evil-my-app.vercel.app")
    assert not re.fullmatch(pattern, "https://my-app.vercel.app.evil.com")


def test_explicit_regex_overrides_the_slug(monkeypatch):
    """Escape hatch for hosts that are not Vercel — Azure Static Web Apps, etc."""
    m = _reload_main(
        monkeypatch,
        VERCEL_PROJECT_SLUG="my-app",
        CORS_PREVIEW_ORIGIN_REGEX=r"^https://x-[a-z0-9]+\.azurestaticapps\.net$",
    )
    assert re.fullmatch(m.PREVIEW_ORIGIN_REGEX, "https://x-abc.azurestaticapps.net")
    assert not re.fullmatch(m.PREVIEW_ORIGIN_REGEX, "https://my-app.vercel.app")


def test_invalid_regex_fails_at_startup(monkeypatch):
    """Better a container that refuses to start than one serving a pattern that
    silently never matches."""
    with pytest.raises(RuntimeError, match="not a valid regular expression"):
        _reload_main(monkeypatch, CORS_PREVIEW_ORIGIN_REGEX="^https://(unclosed")


# ── Logging ──────────────────────────────────────────────────────────────────

def test_logging_goes_to_stdout_not_a_file():
    """Container platforms collect stdout. A log file inside a container is lost
    on restart and invisible while it runs."""
    import main  # noqa: F401  (import configures logging)

    handlers = logging.getLogger().handlers
    assert handlers, "root logger has no handlers; app logs would be discarded"

    streams = [getattr(h, "stream", None) for h in handlers]
    assert any(s is sys.stdout for s in streams), (
        f"no stdout handler on the root logger; got {handlers}"
    )
    file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
    assert not file_handlers, f"logging to files: {file_handlers}"


def test_app_level_logs_are_not_silently_discarded():
    """Default root level is WARNING, which threw away every logger.info() in the
    codebase — including the auth and order paths."""
    import main  # noqa: F401

    assert logging.getLogger().level <= logging.INFO


# ── Entrypoint ───────────────────────────────────────────────────────────────

def test_entrypoint_binds_all_interfaces_on_the_PORT_env_var():
    """127.0.0.1 is unreachable from outside the container, so the platform's
    probe never succeeds and the revision never goes healthy."""
    source = open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
                  encoding="utf-8").read()
    assert '"0.0.0.0"' in source, "entrypoint does not bind all interfaces"
    assert 'os.getenv("PORT"' in source, "entrypoint does not read PORT"
    assert '"8000"' in source, "entrypoint has no 8000 default for PORT"


def test_app_starts_on_a_custom_PORT():
    """Actually boot it, rather than trusting the source read above."""
    env = {**os.environ, "PORT": "8123"}
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        deadline = 40
        last = None
        for _ in range(deadline):
            try:
                r = httpx.get("http://127.0.0.1:8123/health", timeout=2)
                if r.status_code == 200:
                    return
            except Exception as exc:  # not up yet
                last = exc
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                pytest.fail(f"process exited early:\n{out[:2000]}")
            import time
            time.sleep(0.5)
        pytest.fail(f"app did not answer on PORT=8123 in time (last error: {last})")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
