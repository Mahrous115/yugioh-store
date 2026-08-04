-- Migration 002 — stop the browser writing orders directly (AUDIT.md finding H1)
-- Applied to the live project: 2026-08-04
--
-- orders_insert_own granted the `authenticated` role INSERT on public.orders with
-- only WITH CHECK (auth.uid() = user_id). That checks *who* the order belongs to
-- and nothing about what is in it, so any user could run
--     POST /rest/v1/orders  {"user_id": "<self>", "items": [...], "total": 0.01}
-- with the public anon key and forge an order without touching FastAPI. Confirmed
-- exploited on 2026-08-04 (HTTP 201).
--
-- This is the second path to C2. Server-side validation in routers/orders.py is
-- worthless while this policy stands, which is why the two are fixed together.
--
-- Orders are now writable only through the backend, which holds the service-role
-- key and therefore bypasses RLS. With no INSERT policy, RLS denies by default.
--
-- SELECT is deliberately untouched: orders_select_own and orders_select_admin
-- still power order history and the admin analytics dashboard.

DROP POLICY IF EXISTS "orders_insert_own" ON public.orders;

-- Belt and braces: revoke the underlying privilege too, so re-adding a policy by
-- accident does not silently reopen the hole. Mirrors the two-layer approach in
-- migration 001.
REVOKE INSERT, UPDATE, DELETE ON public.orders FROM anon, authenticated;
