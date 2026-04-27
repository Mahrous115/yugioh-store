# Duel Market — Yu-Gi-Oh! E-Commerce Demo

> A full-stack portfolio project showcasing React, FastAPI, Supabase, and third-party API integration.  
> **Live demo:** [https://project-4yktn.vercel.app](https://project-4yktn.vercel.app)

---

## Features

| Feature | Description |
|---------|-------------|
| **Card Catalog** | Browse 12 000+ cards from the YGOPRODeck API with search by name and filters by type, attribute, and race |
| **Card Detail** | Full card stats, description, real market prices (Cardmarket, TCGPlayer), and our custom listing price |
| **Shopping Cart** | Add/remove cards, adjust quantity — persisted in `localStorage` |
| **Mock Checkout** | One-click order placement (no real payment), order saved to Supabase |
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
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Database / Auth | Supabase (PostgreSQL + GoTrue Auth) |
| Card Data | [YGOPRODeck public API](https://ygoprodeck.com/api-guide/) |
| Deployment | Vercel (frontend) + Render (backend) |

---

## Project Structure

```
yugioh-store/
├── frontend/                   # React + Vite app
│   ├── src/
│   │   ├── components/         # Reusable UI components
│   │   ├── context/            # AuthContext, CartContext
│   │   ├── hooks/              # useWishlist, useOrders
│   │   ├── pages/              # One file per route
│   │   ├── services/           # supabase.js, api.js, ygoprodeck.js
│   │   ├── App.jsx             # Router config
│   │   ├── main.jsx            # Entry point
│   │   └── index.css           # Dark-theme global styles
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── backend/                    # FastAPI app
│   ├── models/                 # Pydantic request/response models
│   ├── routers/                # listings.py, wishlist.py, orders.py
│   ├── services/               # supabase_client.py, auth.py
│   ├── main.py                 # App factory + CORS
│   ├── requirements.txt
│   └── .env.example
├── schema.sql                  # Supabase tables + RLS policies
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
3. To make a user an admin, run:
   ```sql
   UPDATE profiles SET role = 'admin' WHERE id = '<user-uuid>';
   ```

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
# Swagger docs at http://localhost:8000/docs
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

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Your Supabase project URL (`https://xxx.supabase.co`) |
| `SUPABASE_SERVICE_KEY` | Service-role key (Settings → API → service_role). **Never expose this in the browser.** |
| `FRONTEND_URL` | Frontend origin for CORS (`http://localhost:5173` locally) |

### Frontend (`frontend/.env`)

| Variable | Description |
|----------|-------------|
| `VITE_SUPABASE_URL` | Same Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Public anon key (safe to expose) |
| `VITE_API_URL` | Backend base URL (`http://localhost:8000` locally) |

---

## Deployment

### Frontend → Vercel

1. Push the repo to GitHub.
2. Import the project on [vercel.com](https://vercel.com).
3. Set **Root Directory** to `frontend`.
4. Add environment variables (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`).
5. Deploy — Vercel auto-detects Vite.

### Backend → Render

1. Create a new **Web Service** on [render.com](https://render.com).
2. Set **Root Directory** to `backend`.
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `FRONTEND_URL` ← your Vercel URL).
6. Deploy.

> After deploying both, update `VITE_API_URL` in Vercel to point at your Render service URL and redeploy.

---

## Architecture Notes

- **Card data** is never stored locally — the frontend calls the YGOPRODeck API directly from the browser. The backend only manages `listings`, `wishlists`, and `orders`.
- **Admin listings** are merged client-side: the catalog fetches cards from YGOPRODeck and checks each card ID against the listings fetched from the backend.
- **Auth** uses Supabase's built-in JWT. The frontend passes the session token as a `Bearer` header; the backend validates it via `supabase.auth.get_user(token)` using the service key.
- **Cart** is stored in `localStorage` — no auth required to browse and add items.
- **RLS** ensures users can only read/write their own wishlist and orders rows, even if they call Supabase directly.
