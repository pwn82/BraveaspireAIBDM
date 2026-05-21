# Connecting Streamlit Cloud to Azure SQL Server

This guide gets you from "no database" to a working cloud SQL Server in ~15 minutes.

## Why not your local SQL Server?

Your machine `LAPTOP-5LTAD0QS\SQLEXPRESS` is behind your home router with no
public IP. Streamlit Cloud's servers cannot reach it. You have three real options:

| Option | Cost | Effort | Verdict |
|--------|------|--------|---------|
| **Azure SQL Database (free tier)** | $0 forever (100K vCore-sec/month) | 15 min | **Recommended** — real SQL Server, cloud-hosted |
| Cloudflare Tunnel to your laptop | $0 | 30 min | Security risk, laptop must stay on 24/7 |
| Self-host SQL Server on a VPS | $5+/month | 1 hour | Overkill — Azure free tier exists |

We'll use **Azure SQL Database free tier** below.

---

## Step 1 — Create the database on Azure (5 min)

1. Sign up at https://azure.microsoft.com/free (no credit card needed for the free SQL tier)
2. Once in the Azure Portal, click **Create a resource** → search for **"Azure SQL"** → **Create**
3. Pick **SQL databases** → **Create**

Fill in the form:

| Field | Value |
|-------|-------|
| Subscription | Free Trial |
| Resource group | Click **Create new** → name it `braveaspire-rg` |
| Database name | `BraveAspireBDM` |
| Server | Click **Create new** |
|  ↳ Server name | `braveaspire` (must be globally unique — try with your name suffix) |
|  ↳ Location | nearest to you (e.g. `Central India`) |
|  ↳ Authentication method | **Use SQL authentication** |
|  ↳ Server admin login | `sqladmin` |
|  ↳ Password | pick a strong password — **save it!** |
| Want to use SQL elastic pool? | No |
| Workload environment | Development |
| Compute + storage | Click **Configure database** → select **General Purpose → Serverless** → tier **GP_S_Gen5_1** → check **"Apply free offer"** (you get 100K vCore-seconds free per month) |
| Backup storage redundancy | Locally-redundant |

Click **Next: Networking**:

| Field | Value |
|-------|-------|
| Connectivity method | **Public endpoint** |
| Allow Azure services to access this server | **Yes** |
| Add current client IP address | **Yes** (so you can test from your laptop) |

Click **Review + create** → **Create**. Wait ~3 minutes for provisioning.

---

## Step 2 — Allow Streamlit Cloud's IP through the firewall (2 min)

Streamlit Cloud uses a range of outbound IPs that change. The easiest fix:

1. In Azure Portal → your SQL Server (not the database, the **server**) → **Networking**
2. Under **Firewall rules** → click **+ Add a firewall rule**:
   - Name: `streamlit-cloud-allow-all`
   - Start IP: `0.0.0.0`
   - End IP: `255.255.255.255`
3. Click **Save**

> **Security note:** This allows any IP to attempt connection. SQL Auth still protects the data (you need username + password). For production, restrict to specific IPs or use Azure Private Endpoint.

---

## Step 3 — Get the connection details

In Azure Portal → your SQL database (`BraveAspireBDM`) → **Connection strings** tab → look at the **ADO.NET** entry. You'll see something like:

```
Server=tcp:braveaspire.database.windows.net,1433;Initial Catalog=BraveAspireBDM;...
```

Note these values:

| You need | From the ADO.NET string |
|----------|------------------------|
| **Server** | `braveaspire.database.windows.net` |
| **Database** | `BraveAspireBDM` |
| **User** | `sqladmin` (what you typed in Step 1) |
| **Password** | what you typed in Step 1 |
| **Port** | `1433` (Azure standard) |

---

## Step 4 — Test the connection locally (2 min)

```bash
pip install pymssql
```

Create a test script `test_azure.py`:

```python
import pymssql
conn = pymssql.connect(
    server="braveaspire.database.windows.net",
    user="sqladmin@braveaspire",     # NOTE: must include @servername for Azure
    password="YOUR_PASSWORD_HERE",
    database="BraveAspireBDM",
    port=1433,
    tds_version="7.4",
)
cur = conn.cursor()
cur.execute("SELECT @@VERSION")
print(cur.fetchone()[0])
conn.close()
```

Run: `python test_azure.py`

You should see: `Microsoft SQL Azure (RTM) - 12.0.x.x ...`

If you get a firewall error, go back to Step 2 and double-check the firewall rule.

---

## Step 5 — Add the secrets to Streamlit Cloud (3 min)

1. Go to https://share.streamlit.io → your app → **⋮ Settings** → **Secrets**
2. Paste this (replace placeholders with your real values):

```toml
# ── Azure SQL Database ─────────────────────────────────────────
AZURE_SQL_SERVER   = "braveaspire.database.windows.net"
AZURE_SQL_DATABASE = "BraveAspireBDM"
AZURE_SQL_USER     = "sqladmin@braveaspire"
AZURE_SQL_PASSWORD = "your-strong-password-from-step-1"
AZURE_SQL_PORT     = "1433"

# ── AI ─────────────────────────────────────────────────────────
AI_PROVIDER     = "groq"
GROQ_API_KEY    = "gsk_your_groq_key"

# ── Apify ──────────────────────────────────────────────────────
APIFY_API_TOKEN = "apify_api_your_token"

# ── Auth ───────────────────────────────────────────────────────
SECRET_KEY      = "any-random-32-char-string"
```

> **CRITICAL** for Azure SQL: the username must be `sqladmin@yourservername` (the `@servername` suffix is mandatory for Azure SQL). Without it, you'll get login failures.

3. Click **Save** → the app auto-reloads.

---

## Step 6 — Verify in your app

Open your deployed Streamlit app. If everything is wired correctly:

- The error `OperationalError ... LAPTOP-5LTAD0QS` is gone
- The login page shows
- Try logging in with `admin@braveaspire.com` / `Admin@123!` (auto-seeded)
- Data you import (companies, contacts, outreach) **persists** across app restarts

Check the Streamlit Cloud logs (Manage app → Logs) — you should see:

```
DB: Azure/Cloud SQL Server (pymssql) → braveaspire.database.windows.net/BraveAspireBDM
```

---

## What happens behind the scenes

The new `db.py` connection priority is:

1. `DATABASE_URL` env var (any SQLAlchemy URL — Postgres, MySQL, whatever)
2. `AZURE_SQL_*` env vars → cloud SQL Server via `pymssql` ← **this is what we just set up**
3. `USE_SQLSERVER=true` + local `pyodbc` → your Windows laptop's SQL Server
4. SQLite fallback

So:
- **Locally on Windows** with `USE_SQLSERVER=true` in `.env` → talks to your laptop's SQL Server
- **On Streamlit Cloud** with `AZURE_SQL_*` set → talks to Azure SQL
- **Anywhere with no config** → SQLite (works but data resets on cloud)

---

## Migrating existing data from your laptop

If you've already added companies/contacts/outreach to your local SQL Server and want to move them to Azure:

### Option A — SQL Server Management Studio (GUI)
1. Open SSMS, connect to your local `LAPTOP-5LTAD0QS\SQLEXPRESS`
2. Right-click `BraveAspireBDM` database → **Tasks** → **Export Data-tier Application** → save as `.bacpac`
3. Right-click the Azure server → **Tasks** → **Import Data-tier Application** → upload the `.bacpac`

### Option B — Just re-run Lead Scraper
The fastest way — let the app rebuild its data from Apify. Takes 30 seconds.

---

## Costs (Azure SQL free tier)

| Resource | Free quota | What you get |
|----------|-----------|--------------|
| vCore-seconds | 100,000 / month | ~28 hours of active queries (plenty for BDM use) |
| Storage | 32 GB | Hundreds of thousands of rows |
| Backup storage | 32 GB | 7-day rolling backup, automatic |

If you exceed the quota the database **pauses** (queries wait) — it doesn't charge you. You'd have to upgrade to Standard tier (~$5/month) to keep it always-on.

---

## Troubleshooting

### "Login failed for user 'sqladmin'"
- Did you include `@yourservername` in `AZURE_SQL_USER`? Azure SQL requires it.
- Wrong password? Reset in Azure Portal → Server → "Reset password".

### "Cannot connect — firewall blocked"
- Re-check Step 2: firewall rule `0.0.0.0` to `255.255.255.255` exists on the **server** (not the database).
- Or: in Azure Portal → SQL Server → Networking → also enable **"Allow Azure services and resources to access this server"**.

### "ModuleNotFoundError: pymssql"
- Streamlit Cloud may have cached an older build. Click **Manage app** → **Reboot** → it'll reinstall.
- Make sure `packages.txt` exists in repo root with `freetds-dev` and `freetds-bin`.

### "TLS handshake failed"
- Add `?tls=1.2` to the connection. Already handled in `db.py` via `tds_version=7.4`.

### App is slow on first request
- Free-tier Azure SQL **auto-pauses** after 1 hour of inactivity. First request after a pause takes ~30 seconds to wake up. After that it's instant.
- Solution: ping the DB every 50 minutes (a simple `SELECT 1` from a cron). Or upgrade to Standard tier.

### Database fills up
- You get 32 GB free. Run `SELECT COUNT(*) FROM companies, contacts, outreach` to check.
- Or just truncate old data: **Settings → 🗄️ Database → Clear All Data**.
