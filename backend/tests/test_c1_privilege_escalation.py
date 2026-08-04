"""Step 2 — a user must not be able to make themselves an admin.

AUDIT.md finding C1, confirmed exploited on 2026-08-04: one PATCH against
/rest/v1/profiles with the public anon key turned an ordinary account into an admin,
which the backend's get_admin_user then trusted completely.

Two layers permitted it and both are asserted here:
  * RLS  — profiles_update_own had no WITH CHECK, so no column was protected
  * GRANT — `authenticated` held UPDATE on profiles.role
"""
import httpx
import pytest

from conftest import ANON_KEY, SUPABASE_URL


def _read_role(user):
    """Read a user's own role through the browser-equivalent anon client."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user.id}&select=role",
        headers=user.rest_headers,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data[0]["role"] if data else None


# ── Behavioural: the actual attack from the audit ────────────────────────────

def test_user_cannot_self_promote_to_admin(api, make_user):
    """The exact exploit from AUDIT.md C1, which must now fail."""
    user = make_user()
    assert _read_role(user) == "user", "new accounts should start as role=user"

    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user.id}",
        headers={**user.rest_headers, "Prefer": "return=representation"},
        json={"role": "admin"},
        timeout=30,
    )

    assert _read_role(user) == "user", (
        f"PRIVILEGE ESCALATION: role became admin via a single PATCH "
        f"(HTTP {r.status_code}: {r.text[:200]})"
    )


def test_self_promotion_attempt_is_rejected_not_silently_ignored(api, make_user):
    """A denied escalation should surface as an error, not a quiet no-op."""
    user = make_user()
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user.id}",
        headers=user.rest_headers,
        json={"role": "admin"},
        timeout=30,
    )
    assert r.status_code >= 400, (
        f"expected an explicit rejection, got HTTP {r.status_code}. "
        "A silent no-op hides the attempt from logs and monitoring."
    )


def test_escalation_attempt_does_not_unlock_backend_admin_endpoints(api, make_user):
    """The downstream half of C1: get_admin_user must keep refusing."""
    user = make_user()
    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user.id}",
        headers=user.rest_headers,
        json={"role": "admin"},
        timeout=30,
    )

    r = httpx.post(
        f"{api}/api/listings/",
        headers=user.api_headers,
        json={
            "card_id": 99999999,
            "card_name": "PYTEST-SHOULD-NOT-EXIST",
            "card_image": "https://example.invalid/x.jpg",
            "price": 0.01,
            "stock": 1,
        },
        timeout=30,
    )

    if r.status_code == 201:  # pragma: no cover - cleanup for a failing run
        httpx.delete(f"{api}/api/listings/{r.json()['id']}", headers=user.api_headers, timeout=30)

    assert r.status_code == 403, (
        f"escalated user reached an admin-only endpoint (HTTP {r.status_code}). "
        "The server-side admin gate is only as trustworthy as the profiles table."
    )


# ── Structural: both layers, independently ───────────────────────────────────

def test_role_column_update_grant_is_revoked(db):
    """Layer 1 — no SQL-level privilege to write profiles.role."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT grantee FROM information_schema.column_privileges "
            "WHERE table_schema = 'public' AND table_name = 'profiles' "
            "AND column_name = 'role' AND privilege_type = 'UPDATE' "
            "AND grantee IN ('anon', 'authenticated')"
        )
        holders = [row[0] for row in cur.fetchall()]

    assert not holders, (
        f"{holders} still hold UPDATE on profiles.role. RLS would be the only thing "
        "standing between a user and an admin role."
    )


def test_profiles_update_policy_pins_the_role_column(db):
    """Layer 2 — RLS itself must reject a role change."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT with_check FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = 'profiles' "
            "AND policyname = 'profiles_update_own'"
        )
        row = cur.fetchone()

    assert row is not None, "profiles_update_own policy is missing entirely"
    with_check = row[0]
    assert with_check is not None, (
        "profiles_update_own has no WITH CHECK, so Postgres reuses USING and any "
        "column may change as long as the row is still yours."
    )
    assert "role" in with_check, (
        f"WITH CHECK does not constrain the role column: {with_check}"
    )


# ── The fix must not break legitimate use ────────────────────────────────────

def test_user_can_still_update_their_own_username(api, make_user):
    """Locking down `role` must not lock down the whole row."""
    user = make_user()
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user.id}",
        headers={**user.rest_headers, "Prefer": "return=representation"},
        json={"username": "renamed-by-test"},
        timeout=30,
    )
    assert r.status_code == 200, f"legitimate username update broke: HTTP {r.status_code} {r.text[:200]}"
    assert r.json()[0]["username"] == "renamed-by-test"


def test_admin_role_still_works_when_set_by_service_key(api, make_user, promote):
    """A genuine admin, promoted server-side, must still pass the admin gate."""
    user = make_user()
    promote(user, "admin")

    r = httpx.post(
        f"{api}/api/listings/",
        headers=user.api_headers,
        json={
            "card_id": 99999998,
            "card_name": "PYTEST-ADMIN-OK",
            "card_image": "https://example.invalid/x.jpg",
            "price": 1.50,
            "stock": 1,
        },
        timeout=30,
    )
    assert r.status_code == 201, f"legitimate admin was locked out: HTTP {r.status_code} {r.text[:200]}"
    httpx.delete(f"{api}/api/listings/{r.json()['id']}", headers=user.api_headers, timeout=30)
