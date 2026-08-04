# Duel Market — Security & Correctness Audit

**Date:** 2026-08-04
**Commit audited:** `885d118` ("open CORS to all origins for Vercel preview URL support")
**Scope:** `backend/` (FastAPI), `frontend/` (React/Vite), `schema.sql`, full git history
**Auditor note:** The audit itself was read-only. Remediation followed separately on
branch `fix/security-audit-findings`; see the status summary below.

---

## Remediation summary

Each finding below keeps its original description and exploit proof as the historical
record. A **STATUS** line has been added to each — the findings are *not* rewritten to
pretend they were never true.

### What was found

Six exploits confirmed by execution against the live stack, plus a schema-drift problem
that had already caused one wrong conclusion in this document. The FastAPI authorization
layer itself was sound: no IDOR, `user_id` never taken from a request body.

### What is closed

| ID | Finding | Fixed in |
|---|---|---|
| **C1** | Self-promotion to admin via `profiles` UPDATE | `bdbd64e` |
| **C2** | Order totals and prices trusted from the request body | `d7a8c2b` |
| **H1** | Browser writes orders straight to Postgres, bypassing the API | `d7a8c2b` |
| **M1** | Wildcard CORS | `ef20a21` |
| **L11** | `schema.sql` drifted from the deployed database | `c679c18` |
| **M2** | — retracted; the finding was wrong (see below) | n/a |

Verified by re-running the original, unmodified `part2.py` probe script:
**6 VULN → 0 VULN**, and by a 38-test integration suite in `backend/tests/`, written
test-first so each fix was seen to fail before it passed.

### What remains open

| ID | Finding | Severity |
|---|---|---|
| **H2** | No rate limiting anywhere | HIGH |
| **H3** | Tokens in `localStorage`; XSS ⇒ persistent account takeover | HIGH |
| **M3** | Auth failures leak internal error strings | MEDIUM |
| **M4** | `/docs`, `/redoc`, `/openapi.json` public | MEDIUM |
| **M5** | No security headers, no CSP | MEDIUM |
| **M6** | Auth costs a network round-trip per request | MEDIUM |
| **L1–L10** | Assorted cleanup — see the LOW section | LOW |

**H3 and M6 are design-level** and are not scheduled: H3 needs a change to how sessions
are stored (or a CSP strong enough to contain it, which **M5** partly addresses), and M6
needs local JWT verification against the project secret instead of a call to Supabase Auth.

---

## Verification status — read this first

**All findings below are now confirmed against the live database and a running stack.**
The earlier `[UNVERIFIED-LIVE]` caveats have been resolved by direct query and by
executing the attacks end to end.

| Label | Meaning |
|---|---|
| **[EXPLOITED-LIVE]** | Attack actually executed against the live stack; succeeded |
| **[CONFIRMED-LIVE]** | Confirmed by querying the live database |
| **[VERIFIED-RUNTIME]** | Reproduced against a locally running backend |
| **[VERIFIED-STATIC]** | Confirmed by reading source; logic is unambiguous |

Live verification was performed with two throwaway accounts
(`audit-<tag>-a@example.com`, `audit-<tag>-b@example.com`), both deleted afterwards.
Row counts returned to their exact pre-audit baseline (profiles 2, wishlists 2,
listings 3, orders 3) with zero leftover test users.

### ⚠️ The deployed schema did NOT match `schema.sql` — *resolved in `c679c18`*

**As found**, `schema.sql` was out of date. The live database carried a policy that did not
appear in the file at all:

```sql
-- LIVE, but absent from schema.sql:
CREATE POLICY "orders_select_admin" ON public.orders FOR SELECT
USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));
```

This retracts one finding (see **M2-RETRACTED**) and *worsens* another (**C1**). Treat
`schema.sql` as documentation of intent, not as the source of truth — anything derived
from it alone is unreliable. Reconciling the file with the live database is itself a
finding (**L11**).

---

## The short version

The FastAPI authorization layer is **better than expected**. Every endpoint that takes a
resource ID has a real server-side check, and no IDOR was found. Someone thought about this.

That work is then undone by two things, **both now demonstrated live**:

1. A user **can make themselves an admin** by updating their own `profiles` row. I did it
   with one HTTP request, then used the escalated account to create and delete listings
   through the backend's own admin-gated endpoints. The admin gate is decorative.
2. The backend is a **thin, trusting proxy in front of a service-role key**. It accepted an
   order for 999 cards worth $5,984 at a total of **$0.01**, and the RLS policies let the
   browser skip the backend entirely and write orders straight to Postgres.

So: the door is locked, but the wall next to it is missing. This is not an untidy codebase —
it has two specific, remotely exploitable defects that a stranger with a free account can hit,
and I hit both of them.

**Live probe results: 6 VULN / 11 PASS / 3 INFO across 20 checks.** The happy path works
end to end; what's broken is that it also works for an attacker.

---

# CRITICAL — exploitable by any stranger who can sign up

## C1. Any authenticated user can promote themselves to admin
**[EXPLOITED-LIVE]** — executed successfully against the live stack on 2026-08-04.

> **STATUS: FIXED** in `bdbd64e` (+ `migrations/001_c1_lock_profile_role_column.sql`).
> Both layers closed: `profiles_update_own` gained a `WITH CHECK` pinning `role` via a
> `SECURITY DEFINER` helper, and table-wide `UPDATE` was revoked in favour of
> `GRANT UPDATE (username)`. Each layer was verified to block on its own — the grant
> layer returns `42501`, and with the grant deliberately restored inside a rolled-back
> transaction RLS still rejects with *"new row violates row-level security policy"*.
> Replaying the exploit chain below now gives `403 / role unchanged / 403`.
> Regression tests: `backend/tests/test_c1_privilege_escalation.py` (7 tests).

```sql
CREATE POLICY "profiles_update_own" ON public.profiles FOR UPDATE USING (auth.uid() = id);
```

The policy restricts *which row* you may update. It does **not** restrict *which columns*.
There is no `WITH CHECK` narrowing the result, and in Postgres an `UPDATE` policy with no
`WITH CHECK` reuses `USING` as the check — so setting `role = 'admin'` still satisfies
`auth.uid() = id` (the `id` never changes). The `CHECK (role IN ('user','admin'))` constraint
on the column explicitly permits `'admin'`.

**Attack** — sign up, then in the browser console of the real site:

```js
await supabase.from('profiles').update({ role: 'admin' }).eq('id', (await supabase.auth.getUser()).data.user.id)
```

The anon key is public by design and RLS is the only thing standing here. Refresh and
`AdminRoute` opens. More importantly the **backend** `get_admin_user` ([auth.py:67](backend/services/auth.py#L67))
reads `role` from this same table, so the attacker now passes the server-side admin check too
and gets full listings CRUD: create, reprice, delete.

**Why this is the top finding:** it converts every "admin only" control in the app into
"any user". The backend role check is implemented correctly and is still bypassed, because
the data it trusts is attacker-writable.

### Confirmed live — the queried policy

```
tablename  | profiles
policyname | profiles_update_own
cmd        | UPDATE
roles      | {public}
using_expr | (auth.uid() = id)
with_check | (NULL - falls back to USING)     <-- no column restriction
```

`with_check` is **NULL**, so Postgres reuses `USING` as the check, and `auth.uid() = id`
stays true while `role` changes. Both layers permit it — there is no column-level `GRANT`
narrowing either:

```
 table_name | column_name |    grantee    | privilege_type
------------+-------------+---------------+----------------
 profiles   | role        | authenticated | UPDATE
```

### Confirmed live — the executed attack chain

Run against the live database with a freshly created, ordinary user account:

| # | Action | Result |
|---|---|---|
| 1 | `PATCH /rest/v1/profiles?id=eq.<self>` with `{"role":"admin"}`, anon key + own token | **HTTP 200** — role `user` → `admin` |
| 2 | `POST /api/listings/` through the backend's `get_admin_user` gate | **HTTP 201** — server-side admin gate **bypassed** |
| 3 | `DELETE /api/listings/{id}` | **HTTP 204** — can destroy catalogue entries |

One request to escalate. The backend then trusts it completely, because
[auth.py:56-61](backend/services/auth.py#L56-L61) reads `role` from the very table the
attacker just wrote to.

### It is worse than `schema.sql` suggests

The live-only `orders_select_admin` policy (see the schema-drift note at the top) means an
escalated user also gains **SELECT on every order in the system** — every customer's purchase
history, item list, and total. Verified live: the escalated test account read **7 orders**
versus the **4** it owned. So C1 is not just "attacker can edit the shop" — it is a
**customer-data breach**.

---

## C2. Order totals and prices are taken from the request body
**[EXPLOITED-LIVE]** — [orders.py:26-31](backend/routers/orders.py#L26-L31), [order.py:5-8](backend/models/order.py#L5-L8)

> **STATUS: FIXED** in `d7a8c2b`, together with **H1** — the two were separate paths to
> the same forgery and fixing either alone would have left the other open.
> The server now looks up every `card_id` in `listings`, rebuilds the line items from
> those rows, and sums the total with `Decimal`. `total` is optional and never trusted;
> when supplied it is only compared, and a mismatch is a 400. `items[]` has a real
> schema with bounds (1–50 lines, quantity 1–99). The audit's exploit request now
> returns 422; the same forgery at a legal quantity returns 400.
> Regression tests: `backend/tests/test_c2_h1_order_integrity.py` (13 tests).

```python
data = {
    "user_id": user.id,      # correct — from the verified token
    "items":   order.items,  # arbitrary client JSON, never validated
    "total":   order.total,  # client-supplied number, never recomputed
}
```

`OrderCreate` is:
```python
items: List[dict]          # no schema at all
total: float = Field(gt=0) # only constraint: must be positive
```

Nothing reads `listings.price`. Nothing recomputes `sum(price * quantity)`. Nothing checks
that the `card_id`s exist, are in stock, or are even listed for sale.

**Attack:**
```bash
curl -X POST http://localhost:8000/api/orders/ \
  -H "Authorization: Bearer <any valid user token>" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"card_id":1,"card_name":"Blue-Eyes","card_image":"x","price":0.01,"quantity":999}],"total":0.01}'
```

**Executed live — HTTP 201.** Ordered **999 × "Dark Magician Girl"** (listed at $5.99, true
value **$5,984.01**) for a recorded total of **$0.01**. The order was accepted, persisted, and
appears normally in order history.

A second probe posted `items: [{"anything": "at all", "nested": {"x": [1,2,3]}}]` — also
**HTTP 201**. `items` being `List[dict]` means the JSONB column accepts arbitrary
attacker-controlled structure of unbounded size, with no card, price, or quantity checking.

**Mitigating context, stated honestly:** checkout is mock — no payment processor, no
fulfilment, so today the loss is integrity of the orders table, not money. But this is the
exact shape of the bug that costs real money the moment a payment step is added, and the
`total` written here is what the admin revenue chart reports.

**The fix direction (not applied):** ignore `total` from the body entirely; look up each
`card_id` in `listings`, recompute the total server-side, and reject on mismatch.

---

# HIGH

## H1. The browser can write orders directly to Postgres, skipping the backend
**[EXPLOITED-LIVE]** — confirmed policy + successful direct insert

> **STATUS: FIXED** in `d7a8c2b` (+ `migrations/002_h1_remove_direct_order_insert.sql`).
> `orders_insert_own` dropped, and `INSERT/UPDATE/DELETE` revoked from `anon` and
> `authenticated` as a second layer so re-adding a policy by accident cannot silently
> reopen it. Orders are now writable only through the backend's service-role client.
> `SELECT` deliberately untouched — order history and admin analytics still work
> (re-verified: a legitimately promoted admin still sees all orders).
> The direct insert now returns `403 / 42501`.

```sql
CREATE POLICY "orders_insert_own" ON public.orders FOR INSERT WITH CHECK (auth.uid() = user_id);
```

The comment above it in `schema.sql` says *"inserts checked via backend service-key"* — but this
policy grants **`authenticated` role INSERT directly**, using the public anon key. Any user can
run `supabase.from('orders').insert({...})` from the console with any `total` and any `items`,
never touching FastAPI.

**Executed live — HTTP 201.** A `POST` straight to `/rest/v1/orders` with only the anon key
and an ordinary user token inserted a forged order (`total: 0.01`), never touching FastAPI:

```
HTTP 201 [{"id":"83d113c0-…","user_id":"…","items":[{"price":0.01,"card_name":"FORGED-DIRECT",…}],"total":0.01}]
```

This is a **second, independent path to C2**. Fixing the validation in `orders.py` alone does
**not** close it — the policy has to be removed or narrowed too. Worth calling out because
"we validated it in the API" is the natural fix and it would leave this wide open.

## H2. No rate limiting anywhere
**[VERIFIED-RUNTIME]** — no limiter middleware present; confirmed absent from `main.py`

> **STATUS: OPEN**

No `slowapi`, no reverse proxy, nothing. `POST /api/orders/` and `POST /api/wishlist/` are
unauthenticated-to-write-cost: a single valid token can insert unbounded rows into your
free-tier Postgres until it fills. Supabase applies its own limits to *auth* endpoints
(signup/login), so credential stuffing is partly covered — but nothing protects your own API.

## H3. Tokens live in `localStorage`, and any origin can call the API
**[VERIFIED-STATIC + VERIFIED-RUNTIME]**

> **STATUS: OPEN — design-level, not scheduled.** The "any origin" half is closed by the
> **M1** fix (`ef20a21`). The storage half needs a change to how sessions are held, or a
> CSP strong enough to contain an XSS (**M5**). Recorded rather than patched, because a
> half-measure here reads as protection without being any.

`supabase-js` defaults to `persistSession: true` with `localStorage` ([supabase.js:7](frontend/src/services/supabase.js#L7)
passes no storage override), so the access **and refresh** tokens are readable by any script
that executes on the page. Combined with the wildcard CORS (M1), any XSS becomes a full,
persistent account takeover — the refresh token is exfiltratable and long-lived.

There is no XSS vector in the current source (no `dangerouslySetInnerHTML`, React escapes by
default), so this is a **latent** risk, not a live one. But `react-router-dom` currently has a
known open-redirect→XSS advisory (see L5), which is exactly the kind of thing that turns it live.

---

# MEDIUM

## M1. CORS allows every origin, method, and header
**[VERIFIED-RUNTIME]** — [main.py:30-36](backend/main.py#L30-L36)

> **STATUS: FIXED** in `ef20a21`. Fixed origins now come from `FRONTEND_URL`
> (comma-separated); Vercel previews are matched by an anchored, https-only pattern built
> from `VERCEL_PROJECT_SLUG`. Methods and headers narrowed to what the API exposes.
> `allow_credentials` stays `False` — auth is a Bearer token, never a cookie.
> Tested against smuggling variants, not just the happy path: `evil-project-4yktn.vercel.app`,
> `project-4yktn.vercel.app.evil.com`, an unrelated `*.vercel.app`, and the plain-http
> downgrade are all refused. Regression tests: `backend/tests/test_m1_cors.py` (13 tests).

You already know this one; recording it with the measured behaviour. A preflight from a
hostile origin:

```
$ curl -X OPTIONS -H "Origin: https://evil.example.com" \
       -H "Access-Control-Request-Method: PUT" \
       -H "Access-Control-Request-Headers: authorization" .../api/listings/abc

access-control-allow-origin: *
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
access-control-allow-headers: authorization
```

**Honest severity note:** the code comment is correct that `allow_credentials=False` plus
Bearer-token auth blocks the classic drive-by CSRF — a malicious page *cannot* make the browser
attach a victim's token. So this is not directly account-compromising on its own, and I am
deliberately **not** ranking it critical. What it does do: let any site on the internet use your
API and replay a token they have obtained by other means, and remove a defence-in-depth layer
that would otherwise blunt H3. `FRONTEND_URL` is already in `.env.example` and is read by
**nothing** — the allowlist it was meant for was never wired up.

## ~~M2. Admin analytics silently reports the wrong numbers~~ — **RETRACTED**
**[CONFIRMED-LIVE — finding was wrong]**

The earlier draft of this audit claimed the admin dashboard would under-report revenue,
because `loadAnalytics()` reads orders through the anon-key browser client
([Admin.jsx:52-55](frontend/src/pages/Admin.jsx#L52-L55)) and `schema.sql` defines only
`orders_select_own`.

**That was wrong.** It was inferred from `schema.sql`, which is stale. The live database has
an additional policy the file does not contain:

```sql
CREATE POLICY "orders_select_admin" ON public.orders FOR SELECT
USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));
```

Verified live: an admin-role account reading through the anon client saw **7 orders** while
owning only **4**. The analytics dashboard works correctly and reports real numbers.

**This is why the schema drift matters** — and note the sting: the same policy that makes
analytics work correctly is what upgrades **C1** from "attacker vandalises the shop" to
"attacker reads every customer's order history".

## M3. Auth failures leak internal error strings to unauthenticated callers
**[VERIFIED-RUNTIME]** — [auth.py:46](backend/services/auth.py#L46)

> **STATUS: OPEN**

```python
raise HTTPException(status_code=401, detail=str(exc)) from exc
```

Measured, with no valid credentials:
```
$ curl -H "Authorization: Bearer garbage.token.here" .../api/orders/
{"detail":"[Errno 11001] getaddrinfo failed"}
```

Raw infrastructure errors reach anonymous clients. Low individual impact, but it hands an
attacker a free oracle into your backend's internal state and dependencies.

**Credit where due:** unhandled 500s do **not** leak. `GET /api/listings/` with a broken
Supabase connection returned exactly `Internal Server Error` with the traceback confined to
server logs. Debug mode is off and that part is correct.

## M4. Interactive API docs are public
**[VERIFIED-RUNTIME]** — `/docs` → 200, `/redoc` → 200, `/openapi.json` → 200

> **STATUS: OPEN**

Full machine-readable map of every endpoint, parameter and schema, served to anyone. Not a
vulnerability by itself; it is a reconnaissance accelerator, and there is no reason for it to
be reachable in production.

## M5. No security headers on any response
**[VERIFIED-RUNTIME]** — 0 of `Strict-Transport-Security`, `X-Frame-Options`,
`X-Content-Type-Options`, `Content-Security-Policy` present.

The only headers the app sets are `Cache-Control: no-store` / `Pragma: no-cache`. A CSP is the
single most valuable one missing here, because it is the mitigation that would contain H3.

> **STATUS: OPEN**

## M6. Every authenticated request makes a network round-trip to Supabase
**[VERIFIED-STATIC]** — [auth.py:19](backend/services/auth.py#L19)

> **STATUS: OPEN — design-level, not scheduled.** Security-wise this is already correct;
> the cost is latency and an availability coupling. Fixing it means verifying the JWT
> locally against the project secret instead of calling Supabase Auth per request.

`supabase.auth.get_user(token)` calls `GET /auth/v1/user` on Supabase.

**Security-wise this is correct, and I want to be precise since you asked:** signature *and*
expiry *are* genuinely verified, on every request, by Supabase itself. There is no local
`jwt.decode(..., verify=False)` anywhere. Token lifetime is Supabase's default (1h access
token, auto-refreshing rotating refresh token — `autoRefreshToken` is on by default and not
overridden). **This is the part of the auth design that is right.**

The problem is operational: every single API call costs an extra round-trip, on a free tier
with rate limits and no caching. If Supabase Auth is slow or unreachable, **every** endpoint
returns 401 (as demonstrated in M3) — an auth outage is indistinguishable from a bad token.
Local verification against the project JWT secret would be both faster and more robust.

---

# LOW / untidy

**L1. Frontend URL paths do not match backend routes.** **[VERIFIED-RUNTIME]**
`api.js` calls `/api/listings/${id}/` and `/api/wishlist/${cardId}/` (trailing slash);
the backend registers `/api/listings/{listing_id}` (none). Measured: `307` redirect, which
curl follows with the `Authorization` header intact, so it currently **works**. It costs a
round-trip per write and depends on browsers preserving auth headers across a post-preflight
redirect. Fragile, not broken.

**L2. JWT prefix and user email written to logs.** [auth.py:16](backend/services/auth.py#L16)
logs the first 30 characters of the token; [auth.py:32](backend/services/auth.py#L32) logs
user id and email. Currently suppressed — uvicorn's default config does not enable INFO for
app loggers, and I confirmed no token text appeared in the log. It becomes a real leak the
moment anyone raises the log level. These are leftover Railway 404 debugging aids, along with
the token-logging `console.log` in [api.js:9-12](frontend/src/services/api.js#L9-L12).

**L3. Zero dependency pinning.** `requirements.txt` lists 5 bare names, no versions, no lockfile.
A fresh install today resolves to **fastapi 0.141.1, starlette 1.3.1, supabase 2.31.0,
pydantic 2.13.4** — substantially newer than what this was written against. It installed and
imported cleanly, and FastAPI's internals have already shifted underneath it (included routers
are now `_IncludedRouter` objects rather than flattened routes). Two identical checkouts a month
apart can get different stacks. Frontend uses caret ranges but does have `package-lock.json`.
*(Not pinning anything, per your instruction.)*

**L4. No tests. None.** No `pytest`, no `vitest`, no test directory, no CI workflow, no
`requirements-dev.txt`. Nothing in this audit was contradicted by a test suite because there
is no test suite. For the two critical findings above, a single test asserting
"a non-admin cannot PUT a listing" and one asserting "a forged total is rejected" would have
caught both.

**L5. 7 npm advisories (3 high).** `vite`, `postcss`, `ws` (high); `esbuild`, `react-router`,
`react-router-dom` (moderate); `@babel/core` (low). Most are dev-server-only, but
**`react-router-dom` open-redirect→XSS is runtime-reachable** and is the one that interacts
badly with H3.

**L6. Deletes report success for things that do not exist.**
[wishlist.py:44](backend/routers/wishlist.py#L44) and [listings.py:47](backend/routers/listings.py#L47)
issue the delete and return `204` unconditionally — no existence check, no rows-affected check.
Callers cannot distinguish "deleted" from "was never there". (`PUT` on listings *does* check
and 404s correctly.)

**L7. `listing_id` is never validated as a UUID.** Typed `str` and passed to PostgREST's `.eq()`.
A malformed id produces a driver-level error surfacing as 500 rather than a clean 400.

**L8. Stock is decorative.** `listings.stock` is displayed and gates the Add-to-Cart button
client-side, but placing an order never decrements it. Orders are also written with no
transaction spanning the stock check, so even a correct implementation would race.
**STATUS: OPEN**

**L9. Dead code from the Railway era.** `NoCacheMiddleware` ([main.py:18-25](backend/main.py#L18-L25))
exists solely to defeat Railway's Fastly CDN, which no longer exists; it now just suppresses
caching on the public listings endpoint for no benefit. `FRONTEND_URL` is configured and never read.

**L10. Errors swallowed in the wishlist context.**
[WishlistContext.jsx:21](frontend/src/context/WishlistContext.jsx#L21) — `catch { /* silently ignore */ }`.
A failing wishlist load renders as an empty wishlist, indistinguishable from genuinely having none.

**L11. `schema.sql` does not match the deployed database.** **[CONFIRMED-LIVE]**
The live DB has 9 policies; the file documents 8. `orders_select_admin` exists in production
and appears nowhere in the repo, so it was applied by hand through the dashboard and never
written back. There are no migration files — `schema.sql` is a one-shot "run this in the SQL
editor" script with no versioning, so there is no record of what was applied when.

This is ranked LOW by direct exploitability and is arguably the **most consequential process
problem in the repo**: it caused a wrong finding in the first draft of this very audit (see
**M2-RETRACTED**). Anyone reasoning about security from the file — including future you — will
reach false conclusions. Adopt Supabase migrations, or at minimum regenerate `schema.sql` from
the live database and keep it current.

> **STATUS: FIXED** in `c679c18`. `schema.sql` reconciled with the live database —
> `orders_select_admin` added, table grants documented for the first time, and the drift
> recorded inline. A `migrations/` directory now holds the SQL actually applied to
> production. `backend/tests/test_schema_sync.py` fails if file and database disagree in
> **either** direction, so this cannot silently recur.

---

# Endpoint-by-endpoint authorization matrix

You said this was what you cared about most. **Every endpoint taking a resource ID is
correctly protected. No IDOR was found.** This is the strongest part of the codebase.

| Method | Path | Guard | Ownership / role enforced? | Verdict |
|---|---|---|---|---|
| `GET` | `/` | none | n/a — health check | ✅ intentional |
| `GET` | `/api/listings/` | none | n/a — public catalogue | ✅ intentional |
| `POST` | `/api/listings/` | `get_admin_user` | role read server-side from `profiles` | ✅ but see **C1** |
| `PUT` | `/api/listings/{listing_id}` | `get_admin_user` | role checked; listings have no per-user owner | ✅ but see **C1** |
| `DELETE` | `/api/listings/{listing_id}` | `get_admin_user` | role checked | ✅ but see **C1** |
| `GET` | `/api/orders/` | `get_current_user` | `.eq("user_id", user.id)` — scoped to token | ✅ correct |
| `POST` | `/api/orders/` | `get_current_user` | `user_id` taken from **token**, not body | ✅ correct — but see **C2** for `total` |
| `GET` | `/api/wishlist/` | `get_current_user` | `.eq("user_id", user.id)` | ✅ correct |
| `POST` | `/api/wishlist/` | `get_current_user` | `user_id` from token, not body | ✅ correct |
| `DELETE` | `/api/wishlist/{card_id}` | `get_current_user` | `.eq("user_id", user.id).eq("card_id", …)` | ✅ correct — cannot delete another user's item |

**Runtime confirmation** — with no credentials: `GET /api/orders/` → **401**,
`GET /api/wishlist/` → **401**, `POST /api/listings/` → **401**.

Two design points worth crediting:
- `user_id` is **never** read from a request body anywhere. It always comes from the verified
  token. That is the single most common IDOR source in apps like this and it was avoided.
- `get_admin_user` ([auth.py:62-64](backend/services/auth.py#L62-L64)) catches *all* exceptions
  and denies with 403 — it **fails closed**. Correct.

## What is and isn't recomputed server-side

| Value | Source | Correct? |
|---|---|---|
| `user_id` on orders | verified JWT | ✅ |
| `user_id` on wishlist items | verified JWT | ✅ |
| `role` for admin checks | `profiles` table, server-side | ✅ mechanism — ⚠️ but the table is user-writable (**C1**) |
| **`total` on orders** | **request body** | ❌ **C2** |
| **`price` per line item** | **request body** | ❌ **C2** — never cross-checked against `listings` |
| `stock` after purchase | never updated | ❌ **L8** |
| Order `id`, `created_at` | database defaults | ✅ |

There is no seller-id concept in this schema (`listings` are admin-owned globally, not
per-seller), so there is no seller-ownership check to audit.

---

# RLS review

**[CONFIRMED-LIVE]** — queried directly against the production database, 2026-08-04.

**RLS is enabled on all four tables.** `relforcerowsecurity` is false on all four, which is
fine — the backend deliberately uses the service role to bypass RLS by design.

```
  relname  | rls_on | rls_forced
-----------+--------+------------
 listings  | t      | f
 orders    | t      | f
 profiles  | t      | f
 wishlists | t      | f
```

Postgres policies are deny-by-default once RLS is on, so any operation with no matching
policy is denied — that structural property holds. **9 policies exist live; `schema.sql`
documents only 8.**

| Table | SELECT | INSERT | UPDATE | DELETE | Assessment |
|---|---|---|---|---|---|
| `profiles` | own row | *(none — denied)* | **own row, ALL columns** | *(none — denied)* | ❌ **C1** — `with_check` NULL, no column scope |
| `wishlists` | own | own | *(none — denied)* | own | ✅ correctly scoped |
| `listings` | `USING (true)` — public | *(none — denied)* | *(none — denied)* | *(none — denied)* | ✅ public read, writes service-key only |
| `orders` | own **+ admin-sees-all** | **own (direct browser write)** | *(none — denied)* | *(none — denied)* | ⚠️ **H1**; admin policy amplifies **C1** |

- `wishlists` and `listings` are correct — verified by live cross-user probes (see Part 2).
- `profiles` UPDATE is the critical hole (**C1**), confirmed exploitable.
- `orders` INSERT contradicts its own `schema.sql` comment and enables **H1**, confirmed.
- **`orders_select_admin` exists live but is absent from `schema.sql`** — see the drift note
  at the top of this document.
- All 9 policies are `PERMISSIVE` and target the `public` role. Since `auth.uid()` is NULL for
  anonymous callers, the `auth.uid() = …` predicates still exclude anon correctly.
- `handle_new_user()` is `SECURITY DEFINER` **with `SET search_path = public`** — correct
  hardening for a definer function, done right. The `on_auth_user_created` trigger is present
  and enabled (`tgenabled = 'O'`), and was observed creating profile rows correctly during testing.

### Table grants are wide open (contributing factor to C1)

`anon` and `authenticated` both hold `SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES,
TRIGGER` on **all four tables**. These are Supabase's permissive defaults, so RLS is doing
*all* of the access control with no `GRANT`-level backstop. Specifically,
`authenticated` has `UPDATE` on `profiles.role`, which is the second half of **C1**.

---

# Secrets review

**Git history: clean.** Verified across all 17 commits on all branches, not just the working tree:

- No `.env` file was ever committed — only `backend/.env.example` and `frontend/.env.example`,
  both containing placeholders.
- `git grep -E "eyJ[A-Za-z0-9_-]{10,}"` across every reachable commit: **no JWT-shaped strings**.
- Searched for `service_role`, `sbp_`, and assigned `SUPABASE_SERVICE_KEY` values: **nothing**.

**Service-role key handling: correct.** It is read only in
[supabase_client.py:13](backend/services/supabase_client.py#L13), from the environment, in
backend code. Grep across `frontend/src`, `frontend/index.html` and `frontend/package.json`
for `SERVICE_KEY` / `service_role`: **zero hits**. The browser bundle reads only
`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` — the anon key is public by
design and correct to ship. The module docstring's claim that the service key is
"never exposed to the browser" holds up.

**Two caveats:**
- `.gitignore` covers `.env` (verified: `git check-ignore` confirms both new `.env` files are
  ignored), but it did **not** cover `*.sql` until this session — a database dump containing
  live user rows sat untracked in the repo root and one `git add -A` would have committed it.
- The database password is now in shell history from this session's `pg_dump`/`psql`
  invocations. It has already been rotated once; rotate again before this repo is shared.

---

# Correctness & test coverage

**[EXECUTED-LIVE]** — full critical path walked against the running stack and live database.
**20 checks: 6 VULN, 11 PASS, 3 INFO.**

| # | Step | Result | Detail |
|---|---|---|---|
| 1 | Sign up | ✅ PASS | Two users created; `handle_new_user` trigger populated `profiles` with `role='user'` correctly |
| 2 | Log in | ✅ PASS | `access_token` 810 chars, `expires_in=3600` (1h), refresh token issued |
| 3 | Browse listings | ✅ PASS | HTTP 200, 3 listings; `price` deserialises as JSON **number**, so `.toFixed()` in the UI is safe |
| 4 | View single listing | ⚠️ INFO | **No `GET /api/listings/{id}` route exists** — returns **HTTP 405**, not 404, because the path only matches `PUT`/`DELETE`. `CardDetail` fetches *all* listings and filters client-side ([CardDetail.jsx:31](frontend/src/pages/CardDetail.jsx#L31)). Fine at 3 rows; degrades linearly. |
| 5 | Add to wishlist | ✅ PASS | HTTP 201; duplicate correctly rejected with 400; read-back scoped correctly |
| 6 | Add to cart | ⚠️ INFO | Client-only (`localStorage`). No server call at all — nothing validates cart prices. Feeds **C2**. |
| 7 | Place order | ✅ PASS | HTTP 201, total $11.98 as submitted |
| 8 | View my orders | ✅ PASS | HTTP 200, correctly scoped to the authenticated user |

**Nothing in the happy path is broken.** Every legitimate step works. The failures are all
security failures, not functional ones:

| Probe | Result |
|---|---|
| **C2** forged total (999 cards for $0.01) | 🔴 **HTTP 201 — accepted** |
| **C2b** arbitrary junk in `items[]` | 🔴 **HTTP 201 — accepted** |
| **H1** direct PostgREST order insert, bypassing backend | 🔴 **HTTP 201 — accepted** |
| **C1** self-promotion to admin | 🔴 **HTTP 200 — role user → admin** |
| **C1** escalated user passes backend `get_admin_user` | 🔴 **HTTP 201 — gate bypassed** |
| **C1** escalated user deletes listings | 🔴 **HTTP 204 — succeeded** |
| **IDOR** User B deletes User A's wishlist item | 🟢 **PASS** — A's item survived; query scoped by `user_id` |
| **IDOR** User B reads A's orders | 🟢 **PASS** — B saw 0 of A's 3 orders |

The two IDOR probes passing is the good news, and it is real: cross-user access control at the
FastAPI layer genuinely works. One wrinkle — the cross-user delete returned **HTTP 204** despite
deleting nothing (**L6**), so a caller cannot tell "denied" from "done".

**Things checked and found genuinely fine:** the frontend builds clean (`vite build`, 807
modules, no errors); the backend imports and serves correctly under the current dependency
set; `CardDetail` properly null-guards a missing listing before dereferencing `listing.price`;
`CheckoutConfirmation` guards against direct navigation; provider nesting in `main.jsx` is correct.

**Missing input validation, consolidated:**
- `OrderCreate.items: List[dict]` — no schema, no length bound, no per-item type checking (**C2**)
- `OrderCreate.total` — bounded only by `> 0`; never reconciled against `items` (**C2**)
- `ListingCreate.card_image: str` — no URL validation; a `javascript:`/`data:` URI is stored
  verbatim and rendered into `<img src>`
- `card_name` — no length bound on any model
- `listing_id` — not UUID-validated (**L7**)
- No bound on wishlist or cart size

**Test coverage: 0%.** No test files, no test framework in either dependency set, no CI.

---

# Fix order

Ranked by *exploitable by a stranger*, not by effort. All three top items are
**confirmed exploited**, not theoretical.

1. **C1** — add `WITH CHECK` to the `profiles` UPDATE policy **and** revoke the `UPDATE` grant
   on `profiles.role` from `authenticated`. Both layers currently permit it. Nothing else
   matters while one HTTP request turns any user into an admin with read access to every order.
2. **C2 + H1** — recompute order totals server-side from `listings`, **and** drop/narrow
   `orders_insert_own`. Two independent paths to the same forgery; fixing only the API leaves
   the direct-to-Postgres route wide open. Give `items[]` a real Pydantic schema while you are there.
3. **L11** — reconcile `schema.sql` with the live database before doing any of the above.
   You cannot safely change policies you do not have an accurate record of, and the drift has
   already produced one wrong conclusion in this audit.
4. **M1** — restore an origin allowlist; `FRONTEND_URL` is already there and already unused.
5. **H2, M3, M5** — rate limiting, stop returning `str(exc)`, add security headers + CSP.
6. **M4, L2** — close `/docs` in production, strip the Railway-era token logging.
7. **L3, L4** — pin dependencies, then write the two regression tests for C1 and C2 first.

Everything else in **LOW** is cleanup and can wait.

---

## Testing methodology

Live verification used two throwaway accounts created via the Supabase admin API with
`email_confirm: true`, exercising the real backend against the real database. No existing
user, order, listing, or wishlist row was read into this document or modified.

**Cleanup verified.** Both test users were deleted (cascading to their profiles, orders, and
wishlist rows) and row counts confirmed back at the pre-audit baseline:

| Table | Before | After |
|---|---|---|
| profiles | 2 | 2 |
| wishlists | 2 | 2 |
| listings | 3 | 3 |
| orders | 3 | 3 |

Zero leftover `audit-*@example.com` users. The escalated test account was demoted to `role='user'`
before deletion. The one test listing created via the escalation chain was deleted by the same
chain that created it (which is itself the proof of finding C1).

**No application code was modified by this audit.**
