-- =============================================================
-- Yu-Gi-Oh! Duel Market — Supabase Schema
-- Run this in your Supabase SQL editor (Dashboard → SQL Editor)
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

-- ─── Row Level Security ──────────────────────────────────────

ALTER TABLE public.profiles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wishlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.listings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders    ENABLE ROW LEVEL SECURITY;

-- profiles: users see / edit only their own row
CREATE POLICY "profiles_select_own"  ON public.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "profiles_update_own"  ON public.profiles FOR UPDATE USING (auth.uid() = id);

-- wishlists: fully private to the owning user
CREATE POLICY "wishlists_select_own" ON public.wishlists FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "wishlists_insert_own" ON public.wishlists FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "wishlists_delete_own" ON public.wishlists FOR DELETE USING (auth.uid() = user_id);

-- listings: anyone can read; writes go through the backend service-key (bypasses RLS)
CREATE POLICY "listings_select_all"  ON public.listings  FOR SELECT USING (true);

-- orders: users see only their own orders; inserts checked via backend service-key
CREATE POLICY "orders_select_own"    ON public.orders    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "orders_insert_own"    ON public.orders    FOR INSERT WITH CHECK (auth.uid() = user_id);
