-- Migration 001 — close the privilege-escalation hole (AUDIT.md finding C1)
-- Applied to the live project: 2026-08-04
--
-- Before this change, any authenticated user could run
--     PATCH /rest/v1/profiles?id=eq.<self>  {"role": "admin"}
-- with the public anon key and become an admin, which the backend's get_admin_user
-- then trusted. Two independent layers permitted it; both are closed here.

-- ── Layer 1: RLS ─────────────────────────────────────────────────────────────
--
-- profiles_update_own had USING (auth.uid() = id) and no WITH CHECK, so Postgres
-- reused USING as the check. Changing `role` kept auth.uid() = id true, so the
-- update passed.
--
-- WITH CHECK can only see the NEW row, so "role must not change" has to be
-- expressed by comparing against the stored value. Reading public.profiles from
-- inside a policy ON public.profiles would recurse ("infinite recursion detected
-- in policy for relation profiles"), so the lookup goes through a SECURITY DEFINER
-- function, which runs as the owner and is therefore not subject to RLS.

CREATE OR REPLACE FUNCTION public.current_profile_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT role FROM public.profiles WHERE id = auth.uid();
$$;

-- Callable by end users, but it only ever reveals the caller's own role.
REVOKE ALL ON FUNCTION public.current_profile_role() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_profile_role() TO anon, authenticated;

ALTER POLICY "profiles_update_own" ON public.profiles
    USING (auth.uid() = id)
    WITH CHECK (
        auth.uid() = id
        AND role IS NOT DISTINCT FROM public.current_profile_role()
    );

-- ── Layer 2: column privileges ───────────────────────────────────────────────
--
-- anon and authenticated held table-wide UPDATE, which covers every column
-- including `role`. Table-level UPDATE cannot be narrowed in place, so it is
-- revoked and re-granted per column.
--
-- `username` is the only column a user has any business changing: `id` is the
-- identity, `created_at` is a server fact, `role` is the privilege itself.

REVOKE UPDATE ON public.profiles FROM anon, authenticated;
GRANT UPDATE (username) ON public.profiles TO authenticated;
