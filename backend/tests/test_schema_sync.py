"""Step 1 — schema.sql must describe the database that is actually deployed.

The audit found `orders_select_admin` live but absent from schema.sql, and that drift
caused a wrong finding (AUDIT.md M2-RETRACTED). These tests fail whenever the file and
the live database disagree, so the drift cannot silently return.
"""
import os
import re

import pytest


# Every test here drives the running backend and a live Supabase project.
pytestmark = pytest.mark.integration

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "schema.sql")


@pytest.fixture(scope="module")
def schema_sql():
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return fh.read()


def _policies_in_file(sql):
    """Policy names declared via CREATE POLICY "name" ... in schema.sql."""
    return set(re.findall(r'CREATE\s+POLICY\s+"([^"]+)"', sql, re.IGNORECASE))


def _live_policies(db):
    with db.cursor() as cur:
        cur.execute("SELECT policyname FROM pg_policies WHERE schemaname = 'public'")
        return {row[0] for row in cur.fetchall()}


def test_every_live_policy_is_documented(db, schema_sql):
    """Anything enforcing access control in production must be in the file."""
    missing = _live_policies(db) - _policies_in_file(schema_sql)
    assert not missing, (
        f"Policies exist in the live database but not in schema.sql: {sorted(missing)}. "
        "Reading the file would understate what the database actually permits."
    )


def test_no_policies_documented_that_do_not_exist(db, schema_sql):
    """The reverse drift: the file promising protection that is not deployed."""
    phantom = _policies_in_file(schema_sql) - _live_policies(db)
    assert not phantom, (
        f"schema.sql declares policies absent from the live database: {sorted(phantom)}. "
        "Reading the file would overstate the protection in place."
    )


def test_rls_enabled_on_all_public_tables(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT relname FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' "
            "AND NOT relrowsecurity"
        )
        unprotected = [row[0] for row in cur.fetchall()]
    assert not unprotected, f"RLS disabled on: {unprotected}"


def test_signup_trigger_documented_and_live(db, schema_sql):
    """The profile-creation trigger is load-bearing for every other policy."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT tgname FROM pg_trigger "
            "WHERE tgrelid = 'auth.users'::regclass AND NOT tgisinternal"
        )
        live = {row[0] for row in cur.fetchall()}

    assert "on_auth_user_created" in live, "signup trigger missing from the live database"
    assert "on_auth_user_created" in schema_sql, "signup trigger missing from schema.sql"


def test_table_grants_are_documented(db, schema_sql):
    """Grants are half of the access-control story and were undocumented entirely.

    C1 needed both a permissive RLS policy *and* an UPDATE grant on profiles.role.
    A file that documents only policies hides half of the attack surface.
    """
    assert re.search(r"\bGRANT\b", schema_sql, re.IGNORECASE), (
        "schema.sql documents no GRANTs at all, yet anon/authenticated hold table "
        "privileges on every table. Half the access-control surface is invisible."
    )
