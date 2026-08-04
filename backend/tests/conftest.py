"""Shared fixtures for the integration suite.

These tests run against the real Supabase project and a locally running backend.
There is no Docker on this machine and no local Supabase Auth, so a live project is
the only way to exercise RLS and JWT verification honestly.

Every test account is created with a unique tag and torn down afterwards; the suite
never reads or mutates pre-existing user data.
"""
import os
import uuid

import httpx
import psycopg
import pytest
from dotenv import load_dotenv

_HERE = os.path.dirname(__file__)
load_dotenv(os.path.join(_HERE, "..", ".env"))
# The anon key lives in the frontend env — it is what a browser would use, and the
# C1/H1 attack paths must be exercised with exactly that key.
load_dotenv(os.path.join(_HERE, "..", "..", "frontend", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
ANON_KEY = os.environ["VITE_SUPABASE_ANON_KEY"]
DB_URL = os.environ["SUPABASE_DB_URL"]
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")

TEST_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="session")
def api():
    """Base URL of the running backend; skips the suite if it is not up."""
    try:
        r = httpx.get(f"{API_URL}/", timeout=10)
        r.raise_for_status()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"backend not reachable at {API_URL}: {exc}")
    return API_URL


@pytest.fixture(scope="session")
def db():
    """Direct Postgres connection for asserting on policies and grants."""
    with psycopg.connect(DB_URL, connect_timeout=30) as conn:
        yield conn


def _service_headers():
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


class TestUser:
    """A throwaway Supabase account, pre-confirmed so it can log in immediately."""

    def __init__(self, email, uid, token):
        self.email = email
        self.id = uid
        self.token = token

    @property
    def api_headers(self):
        """Headers for calling the FastAPI backend as this user."""
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    @property
    def rest_headers(self):
        """Headers for calling PostgREST directly with the public anon key.

        This is what a browser can do, and is the shape of the H1 / C1 attacks.
        """
        return {
            "apikey": ANON_KEY,
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }


@pytest.fixture
def make_user():
    """Factory creating confirmed throwaway users, all deleted on teardown."""
    created = []

    def _make():
        tag = uuid.uuid4().hex[:8]
        email = f"pytest-{tag}@example.com"
        r = httpx.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=_service_headers(),
            json={"email": email, "password": TEST_PASSWORD, "email_confirm": True},
            timeout=30,
        )
        r.raise_for_status()
        uid = r.json()["id"]
        created.append(uid)

        r = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
            json={"email": email, "password": TEST_PASSWORD},
            timeout=30,
        )
        r.raise_for_status()
        return TestUser(email, uid, r.json()["access_token"])

    yield _make

    for uid in created:
        httpx.delete(
            f"{SUPABASE_URL}/auth/v1/admin/users/{uid}",
            headers=_service_headers(),
            timeout=30,
        )


@pytest.fixture
def promote():
    """Set a user's role using the service key, restoring it afterwards.

    Used to test the *authorised* admin path without going through the
    privilege-escalation bug that the suite is asserting is closed.
    """
    touched = []

    def _promote(user, role="admin"):
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user.id}",
            headers=_service_headers(),
            json={"role": role},
            timeout=30,
        ).raise_for_status()
        touched.append(user)

    yield _promote

    for user in touched:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user.id}",
            headers=_service_headers(),
            json={"role": "user"},
            timeout=30,
        )


@pytest.fixture(scope="session")
def listings(api):
    """The live catalogue; several tests need a real card_id and price."""
    r = httpx.get(f"{api}/api/listings/", timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        pytest.skip("no listings in the catalogue to test against")
    return data
