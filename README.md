# Duel Market — Yu-Gi-Oh! E-Commerce Demo

> A full-stack portfolio project showcasing React, FastAPI, Supabase, and third-party API integration.

> **⚠️ No live deployment right now.** The frontend at
> [project-4yktn.vercel.app](https://project-4yktn.vercel.app) is still up, but the Railway
> backend it talked to is gone, so anything needing the API (checkout, wishlist, order
> history, admin) will fail there. **Local is the supported way to run this** — see
> [Local Setup](#local-setup).

---

## Features

| Feature | Description |
|---------|-------------|
| **Card Catalog** | Browse 12 000+ cards from the YGOPRODeck API with search by name and filters by type, attribute, and race |
| **Card Detail** | Full card stats, description, real market prices (Cardmarket, TCGPlayer), and our custom listing price |
| **Shopping Cart** | Add/remove cards, adjust quantity — persisted in `localStorage`, checked against live stock |
| **Mock Checkout** | One-click order placement (no real payment). Priced and stock-checked server-side, order saved to Supabase |
| **User Auth** | Sign up, log in, log out via Supabase Auth with email confirmation |
| **Wishlist** | Authenticated users can save/remove cards; backed by Supabase |
| **Order History** | View all past orders on the profile page |
| **Admin Dashboard** | Protected `/admin` route — CRUD for custom listings (search card → set price + stock) |
| **Price Display** | Read-only Cardmarket / TCGPlayer / eBay / Amazon prices on every card detail page |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, React Router v6, Supabase JS |
| Backend | Python 3.11+, FastAPI, Uvicorn, slowapi |
| Database / Auth | Supabase (PostgreSQL + GoTrue Auth) |
| Card Data | [YGOPRODeck public API](https://ygoprodeck.com/api-guide/) |
| Tests | pytest — 115 integration tests against a real Supabase project |
| Deployment | Frontend on Vercel; **backend not currently deployed** (was Railway) |

---

## Project Structure

```
yugioh-store/
├── frontend/                   # React + Vite app
│   ├── src/
│   │   ├── components/         # Reusable UI components
│   │   ├── context/            # Auth, Cart, Wishlist, Listings
│   │   ├── hooks/              # useWishlist, useOrders
│   │   ├── pages/              # One file per route
│   │   ├── services/           # supabase.js, api.js, ygoprodeck.js
│   │   ├── App.jsx             # Router config
│   │   ├── main.jsx            # Entry point
│   │   └── index.css           # Dark-theme global styles
│   ├── .env.example
│   └── vite.config.js
├── backend/                    # FastAPI app
│   ├── models/                 # Pydantic request/response models
│   ├── routers/                # listings.py, wishlist.py, orders.py
│   ├── services/               # supabase_client.py, auth.py, rate_limit.py
│   ├── tests/                  # Integration suite (see Testing)
│   ├── main.py                 # App factory, CORS, security headers, limiter
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── .env.example
├── migrations/                 # SQL applied to the live database, in order
├── schema.sql                  # Full schema: tables, policies, grants, functions
├── AUDIT.md                    # Security audit + remediation status
└── README.md
```

---

## Local Setup

### Prerequisites
- Node 18+ and npm
- Python 3.11+
- A free [Supabase](https://supabase.com) project

### 1 — Database

1. Open your Supabase project → **SQL Editor**
2. Paste and run the contents of `schema.sql`

`schema.sql` is the complete current state — tables, RLS policies, grants, and the
`place_order` function. For an **existing** database created before those changes, apply
the files in `migrations/` in numerical order instead; each one is idempotent-ish and
documents what it changes and why.

`schema.sql` is expected to match the deployed database exactly. `backend/tests/test_schema_sync.py`
fails if they drift — that drift previously caused a wrong conclusion in `AUDIT.md`, so it
is enforced rather than trusted.

To make a user an admin:
```sql
UPDATE profiles SET role = 'admin' WHERE id = '<user-uuid>';
```
This has to be done with the service role or from the SQL editor. Users **cannot** change
their own `role` — that path was a privilege-escalation bug and is closed at both the RLS
and column-grant level (see `AUDIT.md` C1).

### 2 — Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and fill in SUPABASE_URL and SUPABASE_SERVICE_KEY

uvicorn main:app --reload
# API runs at http://localhost:8000
# Swagger docs at http://localhost:8000/docs — only if ENABLE_DOCS is set (see below)
```

### 3 — Frontend

```bash
cd frontend
npm install

cp .env.example .env
# Edit .env and fill in the three variables

npm run dev
# App runs at http://localhost:5173
```

`VITE_API_URL` defaults to `http://localhost:8000`, so the frontend talks to your local
backend out of the box.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | yes | Your Supabase project URL (`https://xxx.supabase.co`) |
| `SUPABASE_SERVICE_KEY` | yes | Service-role key (Settings → API → service_role). Bypasses RLS. **Never expose this in the browser.** |
| `FRONTEND_URL` | no | CORS allowlist, comma-separated. Default `http://localhost:5173` |
| `VERCEL_PROJECT_SLUG` | no | Project slug used to match preview deploys for CORS. Default `project-4yktn` |
| `ENABLE_DOCS` | no | Set to `true`/`1`/`yes` to serve `/docs`, `/redoc`, `/openapi.json`. **Off by default** |
| `RATE_LIMIT_ORDERS_PER_MIN` | no | Default `5` |
| `RATE_LIMIT_WISHLIST_PER_MIN` | no | Default `10` |
| `RATE_LIMIT_LISTINGS_PER_MIN` | no | Default `30` |
| `RATE_LIMIT_DEFAULT_PER_MIN` | no | Default `300` |
| `SUPABASE_DB_URL` | tests only | Postgres connection string; the test suite asserts on RLS policies and grants directly. Use the **session pooler** host, not `db.<ref>.supabase.co` (IPv6-only) |

### Frontend (`frontend/.env`)

| Variable | Description |
|----------|-------------|
| `VITE_SUPABASE_URL` | Same Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Public anon key (safe to expose — constrained by RLS) |
| `VITE_API_URL` | Backend base URL (`http://localhost:8000` locally) |

---

## Testing

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
# .env needs SUPABASE_DB_URL as well as the usual keys
uvicorn main:app --reload      # the suite talks to a running backend
pytest tests/ -v               # in another terminal
```

115 integration tests. They run against the **real** Supabase project — there is no local
Supabase Auth to run against — so they create throwaway users (`pytest-*@example.com`) and
disposable listings, and delete both on teardown. They never mutate existing data; the
`listings` fixture is read-only and anything that places an order uses `temp_listing`,
because orders now decrement stock.

Coverage is organised by audit finding: `test_c1_privilege_escalation.py`,
`test_c2_h1_order_integrity.py`, `test_m1_cors.py`, `test_m3_auth_error_leakage.py`,
`test_m4_docs_exposure.py`, `test_m5_security_headers.py`, `test_h2_rate_limiting.py`,
`test_l8_stock.py`, plus `test_schema_sync.py`.

---

## Deployment

### Frontend → Vercel

1. Push the repo to GitHub.
2. Import the project on [vercel.com](https://vercel.com).
3. Set **Root Directory** to `frontend`.
4. Add environment variables (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`).
5. Deploy — Vercel auto-detects Vite.

### Backend → not currently deployed

The backend previously ran on Railway. That deployment is gone, and nothing has replaced
it, so the hosted frontend has no API to talk to.

Any host that runs a Python web service will do (Fly.io, Render, Railway again, a VM).
Whatever you pick:

- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Build command:** `pip install -r requirements.txt`
- Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.
- Set `FRONTEND_URL` to your deployed frontend origin — CORS is an **allowlist**, so
  requests from an origin that is not listed (and does not match the Vercel preview
  pattern) are refused. This is not the old `allow_origins=["*"]` setup; forgetting this
  variable will look like the API is broken.
- Leave `ENABLE_DOCS` unset in production.
- Then point `VITE_API_URL` at the new backend URL and redeploy the frontend.

---

## Architecture Notes

- **Card data** is never stored locally — the frontend calls the YGOPRODeck API directly from the browser. The backend only manages `listings`, `wishlists`, and `orders`.
- **Admin listings** are merged client-side: the catalog fetches cards from YGOPRODeck and checks each card ID against the listings held in `ListingsContext`.
- **Listings are shared and refreshable.** They live in one context rather than being fetched per page, because stock changes when anyone checks out — a purchase refreshes them so every view updates together.
- **Auth** uses Supabase's built-in JWT. The frontend passes the session token as a `Bearer` header; the backend validates it via `supabase.auth.get_user(token)` using the service key. Every failure mode returns the same generic 401 — the real cause is logged server-side only.
- **Cart** is stored in `localStorage` — no auth required to browse and add items. Cart prices are a client-side cache and are **not** trusted at checkout.
- **Orders are priced by the server.** `POST /api/orders/` ignores the prices in the request body, looks each `card_id` up in `listings`, and recomputes the total. A client-supplied `total` is only used to detect disagreement, and a mismatch is rejected with 400.
- **Stock is reserved transactionally.** Pricing, the stock check, the decrement and the insert all happen inside the `place_order` Postgres function, so concurrent buyers cannot oversell the last unit. Over-ordering returns 409; an unlisted card returns 400.
- **CORS is an allowlist** built from `FRONTEND_URL` plus an anchored pattern for this project's own Vercel preview deploys. `Retry-After` is explicitly exposed so the frontend can read it off a 429.
- **Rate limits** are per caller (hashed session token, or IP when anonymous), tightest on order creation.
- **RLS** ensures users can only read/write their own wishlist and orders rows, even if they call Supabase directly. Orders are **not** writable from the browser at all — only through the backend's service-role client.
- **Security review.** `AUDIT.md` documents a full audit of this codebase, what was exploitable, what was fixed and in which commit, and the two findings that remain open by decision.
