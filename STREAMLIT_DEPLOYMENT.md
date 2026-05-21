# Deploying to Streamlit Cloud

## The fix you just got

The original error happened because `app/database/db.py` defaulted to connecting
to `LAPTOP-5LTAD0QS\SQLEXPRESS` — your local Windows machine — which is
unreachable from Streamlit Cloud's Linux servers.

Three changes were made:

1. **Default DB is now SQLite** (was SQL Server)
2. **Auto-detects Streamlit Cloud** via `/mount/src` path, env vars, and platform — forces SQLite even if `USE_SQLSERVER=true` is set
3. **`pyodbc` is now optional** — commented out in `requirements.txt` because Streamlit Cloud can't install the underlying Microsoft ODBC driver

After pushing these changes, your app should start cleanly on Streamlit Cloud.

---

## Required: set the right Python version

Streamlit Cloud currently defaults to Python 3.14, which is too new for some
dependencies (`chromadb`, `pyodbc`, `lxml`). Switch to Python 3.11:

1. Open https://share.streamlit.io/
2. Click your app → **⋮ menu** → **Settings**
3. Under **Python version**, select **3.11**
4. Click **Save** — the app will redeploy automatically

The `runtime.txt` file in this repo specifies `python-3.11` as a fallback hint.

---

## Required: set Streamlit Secrets (your API keys)

Since `.env` is now `.gitignored`, you need to add your secrets to Streamlit
Cloud's secrets store:

1. Streamlit Cloud → your app → **⋮** → **Settings** → **Secrets**
2. Paste this template and fill in your real values:

```toml
# AI Provider
AI_PROVIDER     = "groq"
GROQ_API_KEY    = "gsk_your_new_rotated_groq_key"
GROQ_MODEL      = "llama-3.3-70b-versatile"

# Lead Scraping
APIFY_API_TOKEN = "apify_api_your_new_rotated_token"

# Email / SMTP (only if you want to send emails)
SMTP_HOST       = "smtp.gmail.com"
SMTP_PORT       = "587"
SMTP_USER       = "you@gmail.com"
SMTP_PASSWORD   = "your_gmail_app_password"
FROM_EMAIL      = "you@gmail.com"
FROM_NAME       = "BraveAspire AI BDM"

# Database — leave blank to use SQLite (works out of the box).
# For production with persistent data, use a managed Postgres:
#   DATABASE_URL = "postgresql://user:pass@host:5432/dbname"

# Auth
SECRET_KEY      = "generate-a-random-32-char-string-here"

# Optional — only if you actually want SMS OTP
TWILIO_ACCOUNT_SID = ""
TWILIO_AUTH_TOKEN  = ""
TWILIO_FROM_NUMBER = ""
```

3. Click **Save** — the app reloads with new secrets

Streamlit auto-injects everything under `[secrets]` into `os.environ`, so the
existing code that uses `os.getenv("APIFY_API_TOKEN")` etc. just works.

---

## Recommended: use a real database (not SQLite)

**Important:** SQLite on Streamlit Cloud lives on **ephemeral storage**.
Every time your app sleeps or restarts, the file is wiped. All your imported
companies, contacts, outreach, and user accounts will be lost.

For production, point at a managed database — free tiers below are generous:

### Option A: Neon (PostgreSQL — recommended)

1. Sign up at https://neon.tech (free tier: 500 MB, no credit card)
2. Create a project → copy the **Connection string**
3. In Streamlit Cloud Secrets, add:
   ```toml
   DATABASE_URL = "postgresql://user:pass@ep-xxx.aws.neon.tech/dbname?sslmode=require"
   ```
4. Add `psycopg2-binary>=2.9.0` to `requirements.txt`
5. Restart — data now persists forever

### Option B: Turso (SQLite-compatible, distributed)

1. Sign up at https://turso.tech (free tier: 9 GB)
2. Create a database, get the URL + auth token
3. Add `libsql-experimental` to requirements
4. Set `DATABASE_URL = "libsql://your-db.turso.io?authToken=xxx"`

### Option C: Supabase

1. Sign up at https://supabase.com (free tier: 500 MB Postgres)
2. Project → Settings → Database → Connection string
3. Use the same `DATABASE_URL` pattern as Neon

---

## Local development still works the same

On your Windows machine with SQL Server installed:

```bash
# .env (local only, never committed)
USE_SQLSERVER=true
DB_SERVER=LAPTOP-5LTAD0QS\SQLEXPRESS
DB_NAME=BraveAspireBDM
```

And `pip install pyodbc` once. The code detects this and uses SQL Server.

If you don't set `USE_SQLSERVER=true`, you get SQLite locally too (no setup needed).

---

## Troubleshooting

### "ModuleNotFoundError: pyodbc"
- This is fine — `pyodbc` is now optional. The app falls back to SQLite automatically.
- If you want it locally on Windows, uncomment the line in `requirements.txt` and `pip install`.

### "Could not build wheels for chromadb"
- Python 3.14 incompatibility. Switch to Python 3.11 in Streamlit Cloud Settings.

### "Could not build wheels for lxml"
- Same — switch to Python 3.11.

### App loads but database resets every few hours
- SQLite on Streamlit Cloud is ephemeral. Switch to Neon/Turso/Supabase (see above).

### "OperationalError: database is locked" (SQLite)
- Too many concurrent users hitting SQLite. Switch to Postgres.

### Login fails — "Invalid credentials"
- The default `admin@braveaspire.com / Admin@123!` is seeded on first DB init.
- If the DB was wiped (ephemeral SQLite), wait for the app to reseed, or check the logs.

---

## Quick checklist before redeploying

- [ ] `requirements.txt` does NOT have uncommented `pyodbc`
- [ ] `.gitignore` excludes `.env`, `__pycache__/`, `data/*.db`
- [ ] Streamlit Cloud → Python version → 3.11
- [ ] Streamlit Cloud → Secrets → API keys pasted
- [ ] `DATABASE_URL` set to Neon/Turso/Supabase if you want persistent data
- [ ] Rotated Apify + Groq keys (the originals were in the failed push attempt to GitHub)
