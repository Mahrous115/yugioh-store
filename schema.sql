-- =============================================================
-- Yu-Gi-Oh! Duel Market — Supabase Schema
-- Run this in your Supabase SQL editor (Dashboard → SQL Editor)
--
-- THIS FILE MUST MATCH THE DEPLOYED DATABASE.
-- Reconciled against the live project on 2026-08-04. Enforced by
-- backend/tests/test_schema_sync.py, which fails if the two drift apart.
--
-- If you change policies or grants through the Supabase dashboard,
-- mirror the change here in the same session or the suite will fail.
-- =============================================================

-- ─── Tables ─────────────────────────────────────────────────

-- Stores public user data (extends Supabase auth.users)
CREATE TABLE public.profiles (
    id          UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    username    TEXT,
    role        TEXT        NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Cards a user has saved to their wishlist
CREATE TABLE public.wishlists (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    card_id     INTEGER     NOT NULL,
    card_name   TEXT        NOT NULL,
    card_image  TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, card_id)
);

-- Admin-created listings: a card with a custom price and stock level
CREATE TABLE public.listings (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    card_id     INTEGER     NOT NULL UNIQUE,
    card_name   TEXT        NOT NULL,
    card_image  TEXT        NOT NULL,
    price       NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    stock       INTEGER     NOT NULL DEFAULT 0 CHECK (stock >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Orders placed by users at mock checkout
CREATE TABLE public.orders (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    items       JSONB       NOT NULL,   -- array of { card_id, card_name, card_image, price, quantity }
    total       NUMERIC(10, 2) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Auto-create profile on sign-up ─────────────────────────

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, username, role)
    VALUES (NEW.id, NEW.email, 'user')
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ─── Table privileges ────────────────────────────────────────
--
-- These are Supabase's permissive defaults, recorded here because they are half of
-- the access-control story. RLS narrows what these grants allow, but a grant that
-- RLS does not cover is wide open — that combination is exactly what produced the
-- privilege-escalation bug fixed in step 2 (see AUDIT.md, finding C1).
--
-- Supabase applies these automatically to new tables via ALTER DEFAULT PRIVILEGES;
-- they are not issued by this file.
--
-- Verify with:
--   SELECT table_name, grantee, privilege_type
--   FROM information_schema.role_table_grants
--   WHERE table_schema = 'public' AND grantee IN ('anon', 'authenticated');

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.wishlists, public.listings
    TO anon, authenticated;

-- orders is read-only to the browser. Writes go through the backend service key.
-- The INSERT/UPDATE/DELETE privileges are revoked as well as the policy dropped,
-- so re-adding a policy by accident cannot silently reopen H1. See migrations/002.
GRANT SELECT, TRUNCATE, REFERENCES, TRIGGER ON public.orders TO anon, authenticated;

-- profiles is the exception: table-wide UPDATE covered every column, including
-- `role`, which was half of finding C1. See migrations/001. UPDATE is granted
-- per column instead, and `role` is deliberately not among them.
GRANT SELECT, INSERT, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.profiles TO anon, authenticated;
GRANT UPDATE (username) ON public.profiles TO authenticated;

-- ─── Helper: read the caller's stored role without tripping RLS ─────────────
--
-- Used by the profiles_update_own WITH CHECK below. Reading public.profiles from
-- inside a policy ON public.profiles recurses; SECURITY DEFINER runs as the owner
-- and so is exempt from RLS. It only ever discloses the caller's own role.

CREATE OR REPLACE FUNCTION public.current_profile_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT role FROM public.profiles WHERE id = auth.uid();
$$;

REVOKE ALL ON FUNCTION public.current_profile_role() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_profile_role() TO anon, authenticated;

-- ─── Row Level Security ──────────────────────────────────────

ALTER TABLE public.profiles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wishlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.listings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders    ENABLE ROW LEVEL SECURITY;

-- profiles: users see / edit only their own row, and may not change their own role.
--
-- WITH CHECK is what stops privilege escalation (AUDIT.md C1). Without it Postgres
-- reuses USING as the check, and since `id` never changes during a self-update,
-- setting role='admin' passed. WITH CHECK can only see the NEW row, so the stored
-- value is fetched via the SECURITY DEFINER helper above.
CREATE POLICY "profiles_select_own"  ON public.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "profiles_update_own"  ON public.profiles FOR UPDATE
    USING (auth.uid() = id)
    WITH CHECK (
        auth.uid() = id
        AND role IS NOT DISTINCT FROM public.current_profile_role()
    );

-- wishlists: fully private to the owning user
CREATE POLICY "wishlists_select_own" ON public.wishlists FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "wishlists_insert_own" ON public.wishlists FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "wishlists_delete_own" ON public.wishlists FOR DELETE USING (auth.uid() = user_id);

-- listings: anyone can read; writes go through the backend service-key (bypasses RLS)
CREATE POLICY "listings_select_all"  ON public.listings  FOR SELECT USING (true);

-- orders: users read only their own. There is deliberately NO insert policy --
-- orders are written exclusively by the backend, which holds the service-role key
-- and bypasses RLS. RLS denies by default, so the browser cannot write here.
--
-- An orders_insert_own policy previously allowed direct INSERT with the anon key,
-- checking only that user_id matched the caller and nothing about the contents.
-- That let anyone forge an order for any amount without touching FastAPI
-- (AUDIT.md H1). Removed in migrations/002 -- do not reintroduce it. Any pricing
-- validation in routers/orders.py is void while the browser can skip the backend.
CREATE POLICY "orders_select_own"    ON public.orders    FOR SELECT USING (auth.uid() = user_id);

-- Admins read every order — this is what makes the admin analytics dashboard
-- (frontend/src/pages/Admin.jsx) report real figures rather than just the admin's
-- own purchases, since it queries through the anon-key browser client.
--
-- DRIFT NOTE: this policy was applied directly through the Supabase dashboard and
-- was missing from this file until 2026-08-04. Its absence caused a false finding in
-- AUDIT.md (M2-RETRACTED), which claimed admin analytics under-reported revenue.
-- It also widens finding C1: while self-promotion to admin was possible, an attacker
-- gained read access to every customer's order history through this policy.
CREATE POLICY "orders_select_admin"  ON public.orders    FOR SELECT USING (
    EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = auth.uid() AND profiles.role = 'admin'
    )
);
