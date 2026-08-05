# Environment variables — production inventory

Every variable the backend reads, whether it is a secret, and what happens if it is
missing. Intended as the source list for Azure Key Vault / Container Apps config.

Generated 2026-08-05 for the `prep/containerize` work. Verify against source with:

```bash
grep -rnoE "os\.(environ\[|getenv\()[\"'][A-Za-z_][A-Za-z0-9_]*[\"']" \
  --include="*.py" main.py models routers services | sort -u
```

---

## 1. Secrets — Key Vault

Two, and only two. Both are read once at import in `services/supabase_client.py`.

| Variable | Notes |
|---|---|
| `SUPABASE_URL` | Not strictly secret (it is in the frontend bundle), but it belongs beside the key so the pair moves together. |
| `SUPABASE_SERVICE_KEY` | **Genuine secret.** Bypasses RLS entirely — it is the whole security model. Currently an `sb_secret_…` key. Never expose to a browser, never log, never bake into an image layer. |

**Both have no default and the app raises `KeyError` at import if either is missing.**
That is deliberate — failing to start beats starting unauthenticated — but it means a
misconfigured Key Vault reference presents as a **crash-looping revision**, not a runtime
error. If a new revision will not start, check these first.

## 2. Required config — plain env vars, not secrets

| Variable | Default | Set it to |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | *(none)* | Your deployed frontend origin(s), comma-separated. `http://localhost:5173` is always allowed regardless, so this is only for deployed frontends. |

Not strictly required for the process to boot, but the API is useless to a browser
without it: every cross-origin request is refused. This is the variable most likely to
be forgotten, and the failure looks like "the API is down" rather than a config error.

## 3. Optional config — safe defaults

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Listen port. Azure Container Apps sets this to your configured target port. The server always binds `0.0.0.0`. |
| `LOG_LEVEL` | `INFO` | Root log level. Output always goes to stdout. |
| `ENABLE_DOCS` | off | Serves `/docs`, `/redoc`, `/openapi.json`. **Leave unset in production** — it publishes the full API surface. Only `1`/`true`/`yes`/`on` enable it. |
| `FRONTEND_URL` | *(none)* | Legacy name for `CORS_ALLOWED_ORIGINS`; merged with it. Prefer the new name for new setups. |
| `VERCEL_PROJECT_SLUG` | *(none)* | Builds the standard Vercel preview-origin pattern for one project. Unset means no preview origins are allowed. |
| `CORS_PREVIEW_ORIGIN_REGEX` | *(none)* | Full regex for preview origins on a non-Vercel host. Overrides `VERCEL_PROJECT_SLUG`. Anchor it (`^…$`) and require `https`. An invalid regex fails at startup by design. |
| `API_TITLE` | `Yu-Gi-Oh! Duel Market API` | Cosmetic; OpenAPI document only. |
| `API_VERSION` | `1.0.0` | Cosmetic; OpenAPI document only. |
| `RATE_LIMIT_ORDERS_PER_MIN` | `5` | Per caller. Tightest limit — every call writes a row. |
| `RATE_LIMIT_WISHLIST_PER_MIN` | `10` | Per caller. |
| `RATE_LIMIT_LISTINGS_PER_MIN` | `30` | Per caller; admin-only endpoints. |
| `RATE_LIMIT_DEFAULT_PER_MIN` | `300` | Per caller, everything else. `/` and `/health` are exempt. |

## 4. Not needed in the container

| Variable | Where it is used |
|---|---|
| `SUPABASE_DB_URL` | Test suite only — direct Postgres for RLS/grant assertions. **Contains the database password.** Do not ship it to the container; it grants far more than the app needs. |
| `API_URL` | Test suite only; which backend to drive. |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` | Frontend build-time only. Baked into the JS bundle at `npm run build`, so they belong to the frontend pipeline, not this image. |

---

## Minimum viable production config

```
SUPABASE_URL=https://<ref>.supabase.co          # Key Vault
SUPABASE_SERVICE_KEY=sb_secret_…                # Key Vault
CORS_ALLOWED_ORIGINS=https://<your-frontend>    # plain env var
```

Everything else has a working default. `PORT` is supplied by the platform.

## Notes for Azure Container Apps

- **Bind address** is handled in code (`0.0.0.0`); you only need to set the ingress
  target port to match `PORT`.
- **Health probe** should point at `/health`. It returns 200 without touching Supabase,
  so a Supabase outage will not cause the platform to kill healthy replicas. It is also
  exempt from rate limiting, so frequent probing cannot trigger a 429 that reads as
  unhealthy.
- **Logs** go to stdout and are collected automatically. Nothing is written to disk, so
  no volume is required. Uvicorn's own access log goes to stderr, which is also collected.
- **Read-only root filesystem**, if you enable it: the app writes nothing, but CPython
  writes `__pycache__` at import. Set `PYTHONDONTWRITEBYTECODE=1`, or precompile during
  the build. See the filesystem-writes note in the Phase 2 report.
- **Scaling to zero** is safe: there is no in-process state worth preserving. The rate
  limiter keeps its counters in memory, so limits are per replica — with several replicas
  the effective limit is multiplied. Move slowapi to a Redis backend if that matters.
