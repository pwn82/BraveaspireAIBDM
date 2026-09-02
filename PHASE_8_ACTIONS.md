# Phase 8 — Actions You Must Complete

Companion to `AI_BDM_Production_Readiness_Plan.md`. Phase 8 filled the biggest
gaps in test coverage that the plan called out. Coverage measurement is now
wired up (`.coveragerc` + `coverage` package).

---

## Status

| Owner | Task | Status |
|---|---|---|
| Claude | `test_auth.py` — passwords, login, lockout, JWT, refresh tokens | Done (13/13 pass) |
| Claude | `test_tracking.py` — pixel GIF, click redirect, open counter, open-redirect fix | Done (6/6 pass) |
| Claude | `test_agents_workflow.py` — FollowUpAgent contract, workflow compile + state | Done (6/6 pass) |
| Claude | `.coveragerc` wired; `coverage` installed | Done |
| Claude | Full regression across all 9 suites | **88/88 pass** |
| **You** | Wire tests into CI (Phase 9) | Pending — see PHASE_9 when we get there |
| **You** | Grow coverage on modules I marked `<40%` — see §3 | Optional |
| **You** | Decide whether to test IMAP / Vector DB paths (need mocking or live services) | Optional |

---

## 1. Complete test inventory

| Suite | Tests | Covers |
|---|---:|---|
| `test_tenant_isolation.py` | 8 | Phase 1: cross-tenant reads/writes/updates/deletes/FK smuggle |
| `test_rbac.py` | 19 | Phase 3: every role × every router endpoint, 401 vs 403, security headers |
| `test_job_service.py` | 8 | Phase 4: idempotency, retry backoff, DLQ, force_retry, sweeper, cross-org |
| `test_email_safety.py` | 8 | Phase 5: syntax gate, suppression, unsub token, bounce webhook, quota, already_sent |
| `test_ai_gateway.py` | 10 | Phase 6: AIResult, retries, timeout, structured JSON, injection fence, quota |
| `test_billing_quotas.py` | 10 | Phase 7: PLAN_LIMITS, quota gate, webhook idempotency, plan upgrade/downgrade |
| **`test_auth.py`** | **13** | **Phase 8 NEW: hash+verify, login, lockout, JWT, refresh, password change** |
| **`test_tracking.py`** | **6** | **Phase 8 NEW: /track/open, /track/click, open-redirect, unknown ids** |
| **`test_agents_workflow.py`** | **6** | **Phase 8 NEW: FollowUpAgent, cross-tenant guard, workflow compile** |
| **Total** | **88** | |

All 88 tests run in about 20 seconds on my box.

---

## 2. Running the suites

**Every suite, quickest form:**

```bash
for t in tests/test_*.py; do python "$t" ; done
```

**With coverage:**

```bash
pip install coverage
rm -f .coverage
for t in tests/test_*.py; do
  python -m coverage run -a --rcfile=.coveragerc "$t"
done
python -m coverage report --rcfile=.coveragerc
python -m coverage html --rcfile=.coveragerc      # HTML report at htmlcov/index.html
```

**Under pytest** (all suites also run cleanly under it — every test class is
plain `unittest.TestCase`):

```bash
pip install pytest pytest-cov
pytest tests/ --cov=app --cov=backend --cov-report=term
```

---

## 3. Current coverage report

**Overall: 52.0% branch coverage on `app/` + `backend/`** — measured with
`.coveragerc` which deliberately excludes:

- `pages/` and `streamlit_app.py` — not runnable without a Streamlit runtime.
- `alembic/versions/*` — schema declarations, not app logic.
- A handful of never-called agent modules that would report as 0%.

### Strong coverage (>65%)

| Module | Coverage | Note |
|---|---:|---|
| `app/database/models.py` | 100% | Declarative — every line covered on import |
| `app/services/entitlements.py` | 93.5% | Phase 7 tests hit almost every branch |
| `app/agents/followup_agent.py` | 89.4% | Phase 8 agent tests |
| `app/services/job_service.py` | 87.3% | Phase 4 tests |
| `app/services/ai_gateway.py` | 81.7% | Phase 6 tests |
| `backend/routers/companies.py` | 80.8% | Phase 3 RBAC tests |
| `backend/main.py` | 70.0% | Phases 3, 5, 8 combined |
| `app/services/email_service.py` | 65.7% | Phase 5 tests |
| `app/services/crm_service.py` | 65.1% | Phases 1, 7 tests |

### Weak coverage (worth growing)

| Module | Coverage | Why weak | To fix |
|---|---:|---|---|
| `app/services/imap_service.py` | 0% | Needs a live IMAP server | Mock `imaplib.IMAP4_SSL` |
| `app/services/vector_service.py` | 0% | Needs chromadb runtime | Add a chromadb-in-memory test |
| `app/utils/rbac.py` | 0% | Streamlit-tied (imports `st`); tested indirectly via `permissions.py` (72.7%) | Import-under-mock streamlit and exercise `require_auth` / `require_permission` |
| `app/services/scheduler_service.py` | 12.4% | Jobs run in APScheduler event loop | Call `_send_one_followup` etc. directly with fake state |
| `app/workflows/bdm_workflow.py` | 21.8% | Nodes call the real AI and DB in real ways | Sub in a `_StubAI` and stub CRMService — one node at a time |
| `app/services/ai_service.py` | 12.6% | Real provider calls; gateway tests use a FakeAI | Add contract tests that mock the underlying SDK responses |

None of these are P0 blockers — the boundaries that enforce security
(tenant, RBAC, quotas, idempotency) are all tested. The low-coverage
modules are integration paths that need external services (SMTP/IMAP/
Chroma/LLM) or Streamlit — the classic hard-to-test surfaces. Grow them
in Phase 9 when you set up CI (which can provide those services).

---

## 4. What Phase 8 does NOT cover

- **Streamlit page tests.** Streamlit doesn't have a great headless test
  story; the effective coverage there comes from the backend/service tests
  underneath. If a page breaks in the browser it's usually a rendering
  regression, not a logic one.
- **Real LLM integration tests.** Would need budget + live API keys — belongs
  in a nightly CI job, not the fast dev suite.
- **Load tests.** Not in the plan for Phase 8; belongs with observability
  (Phase 10) so we can see what actually slows down.
- **Fuzzing / property-based tests.** Nice-to-have; not a P1.

---

## 5. Test-writing conventions in this repo

If you or a future contributor adds more tests, please keep the shape
consistent — it makes the suite easy to run in bulk:

1. **One temp SQLite DB per suite**, seeded in `setUpClass`. Set
   `DATABASE_URL` before importing anything from `app.*` so `db.py` picks
   it up. Existing tests do this at the top of the file.
2. **Set `DISABLE_SCHEDULER=1`** — otherwise APScheduler tries to start.
3. **Silence the scheduler explicitly** when the test uses TestClient
   (see `tests/test_rbac.py`):
   ```python
   import app.services.scheduler_service as _sched
   _sched.start_scheduler = lambda: None
   _sched.stop_scheduler  = lambda: None
   ```
4. **Never let an ORM object escape its session.** Snapshot to a plain
   dict inside `with get_db()` before returning — otherwise you get
   `DetachedInstanceError` on attribute access.
5. **Every test class is a `unittest.TestCase`** so they also run under
   `pytest` unchanged. Don't mix in raw pytest fixtures.
6. **File names are `test_*.py`** so pytest discovers them and the CI loop
   in section 2 works with `tests/test_*.py`.

---

## Done when

- [ ] `for t in tests/test_*.py; do python "$t"; done` shows every suite `OK`.
- [ ] `python -m coverage report --rcfile=.coveragerc` shows overall ≥50%.
- [ ] You've decided which weak-coverage modules from §3 are worth investing in
      before public launch (my honest take: none are launch-blockers).

When these are checked, Phase 8 is complete and Phase 9 (CI/CD) can wire this
same test loop into a GitHub Actions workflow.
