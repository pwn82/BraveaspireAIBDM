# Setting up Neon PostgreSQL for Streamlit Cloud

**Time:** 5 minutes  •  **Cost:** ₹0 forever  •  **Credit card:** not required

## Why Neon

| Feature | Neon free tier |
|---------|----------------|
| Storage | 3 GB |
| Compute | 0.25 vCPU autoscale |
| Credit card | **Not required** |
| Persistent data | Forever (no expiration) |
| Setup time | ~5 minutes |
| Database type | PostgreSQL 15 (industry standard) |

Your app uses SQLAlchemy, which abstracts the database — so switching from
SQL Server to PostgreSQL is **just one environment variable**. No code changes
needed.

---

## Step 1 — Sign up (1 minute)

1. Open https://neon.tech in your browser
2. Click **Sign up** (top right)
3. Choose **Continue with GitHub** (fastest — uses your existing account) or sign up with email + a strong password
4. Verify your email if you used the email option

No credit card prompt. No "free trial" countdown. You're in.

---

## Step 2 — Create your project (1 minute)

After signing in, Neon shows the **"Create your first project"** screen:

| Field | What to enter |
|-------|---------------|
| **Project name** | `braveaspire-bdm` |
| **Database name** | `braveaspire` (keep it lowercase — Postgres convention) |
| **Postgres version** | 16 (latest stable) |
| **Region** | Pick nearest to your Streamlit Cloud region. **AWS / ap-southeast-1 (Singapore)** is best for India |

Click **Create project**. Neon spins it up in ~10 seconds.

---

## Step 3 — Copy the connection string (30 seconds)

On the new project's dashboard, you'll see a **"Connection string"** box.

It looks like:
```
postgresql://neondb_owner:abc123XYZ@ep-cool-leaf-12345.ap-southeast-1.aws.neon.tech/braveaspire?sslmode=require
```

There may be a toggle to show **"Pooled connection"** vs **"Direct connection"** — use **Pooled connection** (it ends with `-pooler` in the host). This handles Streamlit Cloud's connection patterns better.

**Click the copy icon next to the URL.** This is the only string you need.

---

## Step 4 — Paste into Streamlit Cloud secrets (1 minute)

1. Open https://share.streamlit.io
2. Find your `BraveaspireAIBDM` app → click **⋮** → **Settings** → **Secrets**
3. Add this line to your existing secrets (don't remove the other keys):

```toml
DATABASE_URL = "postgresql://neondb_owner:abc123XYZ@ep-cool-leaf-12345-pooler.ap-southeast-1.aws.neon.tech/braveaspire?sslmode=require"
```

> Paste **the exact string Neon gave you** — including the `?sslmode=require` at the end. This is mandatory for Neon (their servers reject insecure connections).

4. Click **Save**

The app auto-redeploys with the new secret. You'll see in the build logs:

```
DB: using DATABASE_URL → ep-cool-leaf-12345-pooler.ap-southeast-1.aws.neon.tech
```

---

## Step 5 — Verify (30 seconds)

1. Open your deployed app at `https://your-app.streamlit.app`
2. The login screen should appear (no more `OperationalError`)
3. Log in with the default credentials: `admin@braveaspire.com` / `Admin@123!`
4. Go to **Settings → 🗄️ Database** — you should see `Companies: 0  Contacts: 0  Outreach: 0`
5. Click **Load Demo Data** — 8 demo companies appear
6. **Restart the app** (Manage app → Reboot) → demo data is still there

That's persistence. With SQLite, the data would have been wiped on every reboot.

---

## Step 6 — Optional: inspect your data

Neon ships with a SQL editor built into the dashboard:

1. Neon dashboard → your project → **SQL editor** (left sidebar)
2. Type:
   ```sql
   SELECT name, industry, score, status FROM companies ORDER BY score DESC;
   ```
3. Click **Run** — your real CRM data shows up in a table

You can also connect from **DBeaver**, **pgAdmin**, **VS Code SQL Tools**, or any Postgres GUI using the same connection string.

---

## What happens automatically

Your `app/database/db.py` already handles PostgreSQL — no code changes were needed. The flow:

1. App boots, reads `DATABASE_URL` from Streamlit secrets
2. SQLAlchemy detects `postgresql://` prefix → uses `psycopg2` driver
3. SQLAlchemy creates the engine with connection pooling
4. `init_db()` runs → creates all tables (companies, contacts, outreach, users, etc.) automatically via `Base.metadata.create_all()`
5. `_seed_admin()` creates the default super-admin user

First boot may take 15-20 seconds for table creation. Subsequent boots are instant.

---

## Pricing / quotas

| Resource | Free | If you exceed |
|----------|------|---------------|
| Storage | 3 GB | Database **pauses** (no overage charge), upgrade to Launch plan ($19/mo) for more |
| Compute time | 191 hours/month always-on equivalent | Auto-pause kicks in earlier |
| Projects | 1 | Pay for more |
| Branches | 10 | Pay for more |
| Auto-pause | After 5 min idle | Auto-resumes on next query (~500ms) |

For a personal BDM tool, **3 GB will hold ~30 million company rows**. You'll never hit it.

---

## Troubleshooting

### "Connection refused" or "database does not exist"
- Triple-check you pasted the **full** connection string with `?sslmode=require` at the end
- Make sure the database name in the URL matches what you created (e.g. `braveaspire` not `BraveaspireBDM`)

### "FATAL: password authentication failed"
- The password is part of the URL — between `:` and `@`. Copy-paste error?
- Neon dashboard → **Reset password** if unsure

### "SSL connection required"
- Add `?sslmode=require` to the end of your `DATABASE_URL`

### "ModuleNotFoundError: psycopg2"
- Streamlit Cloud may have cached the old build. Manage app → **Reboot** → it'll install `psycopg2-binary` from the updated `requirements.txt`

### First request after a while is slow
- Neon auto-pauses after 5 min idle to save your quota
- First query wakes it up in ~500ms — totally normal
- If you want zero cold-starts, upgrade to Launch plan (~$19/month) or ping `/health` every 2 min from cron

### App still shows the old SQL Server error
- The `AZURE_SQL_*` secrets take priority. Open Streamlit Cloud → Secrets → **delete** all `AZURE_SQL_*` lines so only `DATABASE_URL` is used.

---

## Migrating your existing local data (optional)

If you've been using SQL Server locally and want to move that data to Neon:

### Option A — Just re-run Lead Scraper
The fastest path. Your existing data is mostly Apify-scraped — re-scrape in 30 seconds.

### Option B — `pg_dump` your local SQLite + restore to Neon
```bash
# On your laptop — assumes you've fallen back to SQLite locally:
sqlite3 data/bdm.db .dump > backup.sql
# Hand-clean the .sql (SQLite ↔ Postgres syntax differences) then:
psql "<your-neon-url>" < backup.sql
```

### Option C — Use a tool like pgloader
For SQL Server → Postgres migrations:
```bash
pgloader mssql://user:pass@server/db pgsql://neon-user:pass@neon-host/db
```

---

## Quick reference

| Where to set it | What to set | Example |
|-----------------|-------------|---------|
| Streamlit Cloud → Secrets | `DATABASE_URL` | `postgresql://...neon.tech/braveaspire?sslmode=require` |
| Local `.env` (optional) | Same `DATABASE_URL` | Connects your local dev app to Neon too — useful for testing migrations |

That's it. **No credit card, no Azure form, no 3-step billing wizard.**
