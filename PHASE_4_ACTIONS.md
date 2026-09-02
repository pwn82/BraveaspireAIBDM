# Phase 4 — Actions You Must Complete

Companion to `AI_BDM_Production_Readiness_Plan.md`. Code changes for Phase 4
(durable jobs + idempotency + retries + DLQ + LangGraph checkpoints) are done
and tested. This file lists the ops work only you can do, and — importantly —
what I deliberately did NOT do (Redis+workers) and why.

---

## Status

| Owner | Task | Status |
|---|---|---|
| Claude | `WorkflowRun` model + migration `0003` | Done |
| Claude | Persistent scheduler (SQLAlchemyJobStore) — jobs survive restart | Done |
| Claude | Durable idempotency + retry + DLQ (`app/services/job_service.py`) | Done |
| Claude | Follow-up send idempotent even on restart | Done |
| Claude | LangGraph checkpoints → SQLite / Postgres (fallback: MemorySaver) | Done |
| Claude | Retry sweeper (`_job_retry_sweep` every 5 min) | Done |
| Claude | 8-test reliability suite | **8/8 pass** |
| Claude | Regression check: Phase 1 + Phase 3 tests | **All 35 tests pass** |
| **You** | `pip install -r requirements.txt` to pick up checkpoint packages | Pending |
| **You** | Decide on Redis/worker upgrade path (see below) | Pending — recommended when scaling out |
| **You** | Add dead-letter admin queue to Streamlit UI | Optional |

---

## 1. Install new dependencies

Two packages were added:

- `langgraph-checkpoint-sqlite` — durable LangGraph state when on SQLite
- `langgraph-checkpoint-postgres` — durable LangGraph state when on Postgres

```bash
pip install -r requirements.txt
```

Without them, LangGraph falls back to `MemorySaver` and logs a warning:

```
WARNI [bdm_workflow] LangGraph is using in-memory checkpoints — workflow
      state will be LOST on restart. Install langgraph-checkpoint-sqlite or
      langgraph-checkpoint-postgres for durability.
```

If you see that in prod logs, install the matching package for your DB.

---

## 2. What "durable" means now

Restart the API mid-run and everything survives:

| What | Where it lives | Survives restart? |
|---|---|---|
| Scheduled follow-up triggers | `apscheduler_jobs` table (SQLAlchemyJobStore) | ✅ |
| In-flight follow-up send | `workflow_runs` row + `Outreach.sent_at` guard | ✅ (no double-send) |
| Failed job pending retry | `workflow_runs.next_retry_at` + sweeper | ✅ |
| Dead-lettered job | `workflow_runs.status = 'dead'` | ✅ |
| LangGraph HITL pause | `data/langgraph.sqlite` (dev) / Postgres (prod) | ✅ if checkpointer installed |

Test it yourself:

```bash
# Terminal 1
uvicorn backend.main:app --reload
# ... in Streamlit, kick off an AI workflow that pauses at Human Review.

# Terminal 2 (any time later)
# Restart terminal 1's uvicorn.
# The HITL state is still there — resume via the Workflow page.
```

---

## 3. What I did NOT do (and why): Redis + workers

The plan lists Redis+Celery / Redis+RQ / SQS / etc. as production options.
I chose SQLAlchemyJobStore instead. The trade-off:

| | SQLAlchemyJobStore (chosen) | Redis + workers (deferred) |
|---|---|---|
| Setup cost | Zero — uses your existing DB | Add Redis + a worker process |
| Deploys on Streamlit Cloud? | ✅ | ❌ (no Redis) |
| Multi-process safe? | Partial — DB locks around each poll | ✅ |
| Job runs in API process? | ✅ | ❌ (dedicated worker) |
| Long/blocking jobs block API? | ⚠️ Yes — same event loop | ❌ (isolated worker) |
| Ready for `uvicorn --workers 4`? | ⚠️ Each worker runs its own scheduler | ✅ |

**Verdict:** SQLAlchemyJobStore is a real improvement — you go from "jobs die
on restart" to "jobs are durable, retried, deduped." That's the P0 win the
plan asks for. Redis+workers is the *next* upgrade when either (a) you scale
past one process, or (b) a job body starts blocking the API for real time.

### Upgrade path when the time comes

The `job_service.run_job(...)` API doesn't change. Only the *dispatch* changes:

1. Install redis + a queue library (RQ is simplest).
2. Replace `SQLAlchemyJobStore` with `RedisJobStore`, or drop APScheduler and
   have `_job_send_followups` etc. push to an RQ queue.
3. Run one or more worker processes: `rq worker` (or `celery worker`).
4. `run_job(...)` still wraps every job body — you keep idempotency, retries,
   DLQ, cross-org isolation for free.

Do NOT do this until you're actually deploying to a host that supports Redis
(Railway, Render, self-hosted). Doing it "just in case" turns a working
single-process app into a broken multi-service one.

---

## 4. Retry policy

Configured in `app/services/job_service.py` (`_BACKOFF`):

| Attempt | Delay | Total elapsed |
|---:|---:|---:|
| 1 (first fail → retry) | 60 s | 1 min |
| 2 | 5 min | 6 min |
| 3 | 30 min | 36 min |
| 4+ | (none — dead-letter) | — |

Jitter: ±15% so a burst of failures doesn't stampede back at the same second.
Adjust the `_BACKOFF` list to change the schedule; tests will still pass.

The retry sweeper runs every 5 minutes. On a really tight retry (60 s), the
actual re-run may land up to 5 min late. That's fine for our workload; if
you need sub-minute retries later, drop the sweep interval.

---

## 5. Dead-letter queue

Failed jobs beyond `max_retries` land in `workflow_runs` with `status='dead'`.
No admin UI ships in this phase — inspect them with:

```python
from app.services.job_service import get_dead_letters, force_retry
get_dead_letters(organization_id=1)   # inspect
force_retry(run_id=42)                # rearm one manually
```

**Recommended follow-up:** add a "Dead-letter queue" panel to Settings that
lists these rows and lets an admin click "Retry" or "Discard". Small piece
of work — hook `get_dead_letters()` into a table, `force_retry()` behind a
button. I did not do this in Phase 4 because Phase 4 was already large.

---

## 6. What Phase 4 does NOT cover

- **Cross-worker locking.** If you run `uvicorn --workers N`, each worker
  starts its own APScheduler. Two workers may fire the same trigger at the
  same second — but the `run_job` idempotency layer catches that (second one
  gets `skipped_duplicate`). It's inefficient (wasted DB round-trip) but
  correct. Redis-backed queues solve this properly.
- **Distributed transactions.** `run_job` uses DB-level row updates for
  status transitions. Two workers racing to "running" resolve by "last write
  wins" — but the underlying function still runs once because idempotency
  is checked before "running" is set. If the same key is genuinely fired
  concurrently by two workers you may occasionally see the fn run twice.
  Rare, but if it matters, add `SELECT FOR UPDATE` around the status check.
- **Job priority / QoS.** APScheduler is FIFO within a trigger. No priorities.
- **Long-running async jobs** (minutes+). They block the FastAPI event loop.
  Real fix is a worker process — see section 3.

---

## Done when

- [ ] `pip install -r requirements.txt` has run; no `MemorySaver` warning at boot.
- [ ] `python tests/test_job_service.py` shows `Ran 8 tests ... OK`.
- [ ] Manually verified: start API, schedule a follow-up, kill API, restart —
      the trigger is still in `apscheduler_jobs`.
- [ ] Manually verified: force a follow-up to a bad SMTP host — after 3 failed
      retries it appears in `get_dead_letters(...)`.
- [ ] (Optional) Added a dead-letter panel to the Settings page.

When these are checked, Phase 4 is genuinely complete. Phase 5 (email
suppression + unsubscribe + bounce + reply threading) is next.
