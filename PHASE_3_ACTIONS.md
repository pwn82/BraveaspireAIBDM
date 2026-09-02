# Phase 3 — Actions You Must Complete

Companion to `AI_BDM_Production_Readiness_Plan.md`. Code changes for Phase 3
(FastAPI RBAC + security headers + rate limiting) have been made and tested.
This file lists the ops work only you can do: set production env vars,
configure allowed origins, and (optionally) upgrade the rate limiter for
multi-worker deployments.

---

## Status

| Owner | Task | Status |
|---|---|---|
| Claude | Extract permissions catalog to Streamlit-free module | Done |
| Claude | `require_permission(perm)` FastAPI factory | Done |
| Claude | Every router endpoint has correct permission | Done |
| Claude | Security headers middleware | Done |
| Claude | In-memory rate limiter (dev-grade) | Done |
| Claude | CORS: explicit allowlist, no wildcard-with-credentials | Done |
| Claude | Basic open-redirect protection on `/track/click` | Done |
| Claude | Pin `starlette<0.40` (env drift with FastAPI 0.115) | Done |
| Claude | 19-test RBAC test suite (4 unit + 15 end-to-end) | **19/19 pass** |
| **You** | Set `CORS_ALLOW_ORIGINS` in production env | Pending |
| **You** | Set `APP_ENV=production` in production env | Pending |
| **You** | Consider Redis-backed rate limiting for multi-worker deploys | Recommended |
| **You** | Run `pip install -r requirements.txt` (or the starlette command below) | Pending |

---

## 1. Install the pinned Starlette

Starlette 1.6 (released recently) dropped `Router(on_startup=…)` which
FastAPI 0.115 still calls. That broke `backend.main` imports on every dev
machine that ran `pip install`. Requirements now pin `starlette>=0.27,<0.40`.

```bash
pip install -r requirements.txt
```

or targeted:

```bash
pip install "starlette>=0.27,<0.40"
```

You'll see a warning that Streamlit wants `starlette>=0.40`; ignore it —
Streamlit still works fine at 0.39.2. When we upgrade to a FastAPI release
that uses lifespan handlers (>=0.116 when it lands), the pin can widen.

---

## 2. CORS allowlist (production)

`backend/main.py` reads `CORS_ALLOW_ORIGINS` at startup — comma-separated
list of allowed frontends. In production, this must be a real allowlist:

```
CORS_ALLOW_ORIGINS=https://app.braveaspire.com,https://staging.braveaspire.com
```

The app refuses to boot in production if `CORS_ALLOW_ORIGINS` contains `*`
— a wildcard combined with `allow_credentials=True` is silently rejected by
browsers, giving false security. Explicit allowlist only.

Local dev default is `http://localhost:8501,http://127.0.0.1:8501` — no
action needed.

---

## 3. Production env checklist

Set these on your hosting platform (Streamlit Cloud secrets, Railway env, etc.):

| Env var | Value | Why |
|---|---|---|
| `APP_ENV` | `production` | Enables HSTS header, refuses insecure `SECRET_KEY`, refuses CORS wildcards |
| `SECRET_KEY` | 64-byte urlsafe token (Phase 0) | JWT signing |
| `DATABASE_URL` | `postgresql://...` (Phase 2) | Real DB |
| `CORS_ALLOW_ORIGINS` | Your real frontend origins | See above |
| `RATE_LIMIT_GENERAL` | `100` (default) | Per-IP req/min for `/api/*` |
| `RATE_LIMIT_AUTH` | `10` (default) | Per-IP req/min for `/api/auth/*` |

---

## 4. Rate limiter: dev vs prod

**Current implementation** is an in-memory sliding window per IP. Sufficient
for a single uvicorn worker. Two known limits:

1. **Multiple workers** (e.g. `uvicorn --workers 4`) each maintain their own
   counters, so effective ceiling is `N × RATE_LIMIT` instead of `RATE_LIMIT`.
2. **App restart** clears the counter; a client can attempt a burst around
   every deploy.

For production with multiple workers, replace with a Redis-backed limiter.
This is a Phase 4 task — I did not do it here because Phase 4 introduces
the Redis / queue infrastructure the plan calls for, and adding a Redis
dependency just for rate-limiting when the rest of Phase 4 will need it too
is churn.

If you're deploying with a single worker (Streamlit Cloud does this), the
current limiter is fine.

---

## 5. Security headers — what's set

Every response from the API now includes:

| Header | Value | Purpose |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Blocks MIME-sniffing |
| `X-Frame-Options` | `DENY` | Blocks clickjacking via `<iframe>` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Reduces info leaked in Referer |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | Disables features you don't use |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | HSTS — **prod only, over HTTPS** |

HSTS is deliberately not set in dev (would poison localhost for a year).
`APP_ENV=production` enables it.

Not set (intentional):
- **Content-Security-Policy** — the API returns JSON, CSP is a page-level
  concern. Add it to the Streamlit frontend when you deploy that behind a
  reverse proxy (Nginx / Cloudflare).

---

## 6. What Phase 3 does NOT cover

- **Streamlit page hardening.** The Streamlit UI still uses `rbac.require_permission`
  which halts rendering — but Streamlit is not the security boundary. The
  API is. Never rely on hidden UI buttons.
- **Ownership checks on individual rows.** These are already enforced by
  Phase 1's tenant-scoped CRMService — an Org A user can only touch Org A
  rows even at admin role. If your product ever needs sub-tenant ownership
  ("only the creator can edit"), that's a per-row check to add later.
- **OAuth / SSO.** JWT is the current mechanism. If you add Google/Microsoft
  login later, it should still issue the same JWT format so `require_permission`
  keeps working unchanged.

---

## Done when

- [ ] `pip install -r requirements.txt` has run on your machine.
- [ ] `python tests/test_rbac.py` shows `Ran 19 tests ... OK` on your machine.
- [ ] `CORS_ALLOW_ORIGINS` set in production env (never `*`).
- [ ] `APP_ENV=production` set in production env.
- [ ] Verified in browser DevTools that responses from your prod API include
      `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`.
- [ ] Confirmed you can hit `/api/companies/` with a bearer token, and it
      returns 401 without one, 403 with a viewer role trying to POST.

When all six boxes are ticked, Phase 3 is complete.

---

## Reference — endpoints and required permissions

| Endpoint | Method | Permission |
|---|---|---|
| `/api/companies/` | GET | `company.read` |
| `/api/companies/` | POST | `company.create` |
| `/api/companies/{id}` | PUT | `company.update` |
| `/api/companies/{id}` | DELETE | `company.delete` |
| `/api/companies/industries` | GET | `company.read` |
| `/api/contacts/` | GET | `contact.read` |
| `/api/contacts/` | POST | `contact.create` |
| `/api/contacts/{id}` | PUT | `contact.update` |
| `/api/outreach/` | GET | `outreach.read` |
| `/api/outreach/` | POST | `outreach.create` |
| `/api/outreach/{id}` | PUT | `outreach.create` |
| `/api/outreach/followups` | GET | `followup.read` |
| `/api/analytics/pipeline` | GET | `analytics.read` |
| `/api/analytics/tracking` | GET | `analytics.read` |
| `/api/analytics/audit-logs` | GET | `user.read` |
| `/api/auth/login` | POST | (public — rate-limited) |
| `/api/auth/register` | POST | (public — rate-limited) |
| `/health` | GET | (public) |
| `/webhooks/stripe` | POST | (Stripe signature — no auth) |
| `/track/open/{id}`, `/track/click/{id}` | GET | (public — tracking pixels) |
