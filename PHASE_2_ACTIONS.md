# Phase 2 — Actions You Must Complete

Companion to `AI_BDM_Production_Readiness_Plan.md`. Code changes for Phase 2
(Alembic migrations + hot-path indexes + migration runner) have already been
made. This file lists the ops-side work only you can do: stand up PostgreSQL,
cut the app over to it, and test backup/restore.

**Why this matters:** SQLite works for local dev, but it does not scale, does
not support concurrent writes safely, and cannot be backed up with the same
tools the rest of your stack uses. Production must run on PostgreSQL.

---

## Status

| Owner | Task | Status |
|---|---|---|
| Claude | Add Alembic to requirements | Done |
| Claude | `alembic.ini` + `alembic/env.py` reuse app's `DATABASE_URL` | Done |
| Claude | `0001_baseline.py` — full schema snapshot | Done |
| Claude | `0002_production_indexes.py` — hot-path composite indexes | Done |
| Claude | `init_db()` runs Alembic (auto-stamps legacy DBs) | Done |
| Claude | Verified fresh / legacy / at-head scenarios work | Done |
| Claude | Verified Phase 1 tenant isolation still passes | Done |
| **You** | Provision production PostgreSQL | Pending |
| **You** | Set `DATABASE_URL` in production env | Pending |
| **You** | Run first `alembic upgrade head` against production | Pending |
| **You** | Configure daily backups | Pending |
| **You** | Test restore from backup | Pending |

---

## 1. Provision PostgreSQL

You already added Neon support in commit `9b43850`. If Neon is what you're
using, you already have a connection string. Otherwise, pick one of:

| Provider | Free tier? | Best for |
|---|---|---|
| Neon | Yes (0.5 GB) | Serverless PG, branching, no credit card |
| Supabase | Yes (0.5 GB) | Managed PG + auth/storage extras |
| Railway | Trial credit | Full stack in one dashboard |
| Render | Yes (90 days) | Simple managed PG |
| AWS RDS / Azure Postgres / Google Cloud SQL | Paid | Enterprise / when infra is already there |
| Self-hosted (Docker) | Free | Dev-adjacent staging, not for prod |

Whatever you pick, you end up with a connection string that looks like:

```
postgresql://user:password@host:port/dbname?sslmode=require
```

Do NOT paste it into a committed file. Set it as an env var in your hosting
provider's dashboard (Streamlit Cloud → app settings → secrets, or the equivalent).

---

## 2. Point the app at PostgreSQL

In production, set exactly one env var:

```
DATABASE_URL=postgresql://user:password@host:port/dbname?sslmode=require
```

Nothing else. `app/database/db.py` already prefers `DATABASE_URL` over every
other option. The Alembic env.py reads the same variable.

Local dev keeps working: leave `DATABASE_URL` unset and the app falls back to
SQLite at `data/bdm.db`.

---

## 3. Run migrations against production

Two options. Pick one.

### Option A — Let the app do it on first boot (recommended)

`init_db()` now runs `alembic upgrade head` automatically. If your production
PostgreSQL is brand new (no tables), the first request to the app creates
every table and stamps to `0002`. You don't have to do anything.

Verify after first boot:

```bash
DATABASE_URL="postgresql://..." python -m alembic current
```

Expected output: `0002 (head)`.

### Option B — Run migrations manually before deploy (safer for prod)

```bash
DATABASE_URL="postgresql://..." python -m alembic upgrade head
```

Then deploy the app. This is safer because a migration failure surfaces in
your terminal, not as a broken app booting for the first time.

---

## 4. Adding new migrations later

When you change a model in `app/database/models.py`:

```bash
python -m alembic revision --autogenerate -m "short description of change"
```

Then **open the generated file** in `alembic/versions/` and review it before
committing. Autogenerate is not perfect — it can miss server-side defaults,
enum changes, and constraint reorders. Read the diff, adjust if needed, then:

```bash
python -m alembic upgrade head    # apply locally
git add alembic/versions/xxxx_*.py
git commit -m "add migration for <change>"
```

To roll a migration back:

```bash
python -m alembic downgrade -1    # undo the most recent migration
python -m alembic downgrade base  # nuke everything (dev only!)
```

---

## 5. Backups

**PostgreSQL managed providers:** point-in-time recovery is usually enabled
by default. Check your provider dashboard — Neon and Supabase both retain
7 days of history on the free tier. Turn on daily snapshots if not on.

**Self-hosted PostgreSQL:** schedule `pg_dump` to run daily and ship the
output somewhere durable (S3, GCS, Backblaze). Example cron:

```bash
0 3 * * * pg_dump --format=custom --file=/backups/braveaspire-$(date +%Y%m%d).dump $DATABASE_URL
```

**Local SQLite (dev only):** the file `data/bdm.db` is your database. Copy it.

```bash
cp data/bdm.db data/bdm.db.bak-$(date +%Y%m%d)
```

---

## 6. Test restore

**Untested backups are theatre.** Before you consider Phase 2 complete, test
that a backup restores cleanly against a scratch database.

### PostgreSQL

```bash
# Restore into a NEW database (never into the live one).
createdb braveaspire_restoretest
pg_restore --dbname=braveaspire_restoretest /backups/braveaspire-20260901.dump

# Verify some tenant data survived.
psql braveaspire_restoretest -c "SELECT COUNT(*) FROM companies;"
psql braveaspire_restoretest -c "SELECT name, slug FROM organizations;"

# Clean up.
dropdb braveaspire_restoretest
```

### SQLite

```bash
cp data/bdm.db.bak-20260901 /tmp/restoretest.db
sqlite3 /tmp/restoretest.db "SELECT COUNT(*) FROM companies;"
sqlite3 /tmp/restoretest.db "SELECT name, slug FROM organizations;"
```

---

## 7. What NOT to do

- Do **not** delete `alembic/versions/0001_baseline.py` even if it looks
  weird. It's the anchor every subsequent migration chains from. Every DB
  that ever ran the app pins its schema to a revision in this chain.
- Do **not** edit an already-shipped migration. If you need to change
  something, add a new migration. Editing a shipped migration means
  developers/servers on different revisions can never agree on what "the
  schema" is.
- Do **not** commit `data/bdm.db`. It's a per-machine dev artifact. Add it
  to `.gitignore` if it isn't already (line already exists as `data/*.db`).
- Do **not** point the app at PostgreSQL without first setting a new
  `SECRET_KEY` (Phase 0 requirement) — a new DB with the leaked SECRET_KEY
  still forges valid JWTs against the new user table.

---

## Done when

- [ ] Production PostgreSQL is up and reachable.
- [ ] `DATABASE_URL` set in production env (never committed).
- [ ] `alembic current` on prod shows `0002 (head)`.
- [ ] Daily automated backups configured.
- [ ] Backup restore tested against a scratch DB and passes a data sanity check.
- [ ] App boots against PostgreSQL without falling back to SQLite (check logs
  for `DB: using DATABASE_URL → ...` — no `SQLite default` messages).

When all six boxes are ticked, Phase 2 is complete and the plan's Phase 3
(API RBAC enforcement at endpoint level) is next.

---

## Reference — migration commands cheat sheet

```bash
# Where am I?
python -m alembic current

# Full history, most-recent first.
python -m alembic history --verbose

# Apply all pending migrations.
python -m alembic upgrade head

# Roll back one step.
python -m alembic downgrade -1

# Generate a new migration from model changes.
python -m alembic revision --autogenerate -m "description"

# Generate an empty migration you'll hand-write.
python -m alembic revision -m "description"

# Dry-run: print the SQL that upgrade head would execute, without running it.
python -m alembic upgrade head --sql
```
