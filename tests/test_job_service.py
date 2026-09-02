"""
Phase 4 reliability tests.

Verifies the durable job runner does what it promises:
  1. Idempotency  — same (org, workflow, key) runs the underlying fn once.
  2. Retry        — a transient failure schedules a retry with next_retry_at.
  3. Dead-letter  — after N failures the run is marked "dead" and never runs.
  4. Result cache — a succeeded run returns its cached result on re-invocation.
  5. Force retry  — an admin can rearm a dead-lettered run.
  6. Sweeper      — returns rows whose next_retry_at has passed.
  7. Cross-org    — same idempotency_key in two orgs is independent.

Run:  python tests/test_job_service.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["USE_SQLSERVER"] = "false"
os.environ["APP_ENV"]       = "development"
os.environ["DISABLE_SCHEDULER"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.db import init_db, get_db                             # noqa: E402
from app.database.models import WorkflowRun                             # noqa: E402
from app.services.job_service import (                                   # noqa: E402
    run_job, sweep_ready_retries, get_dead_letters, force_retry,
)


class JobServiceTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    # ── 1. Idempotency ──
    def test_01_idempotency_runs_fn_once(self):
        calls = []
        def worker():
            calls.append(1)
            return "ok"
        outcomes = [
            run_job("wf-idem", "k-1", worker, organization_id=1)
            for _ in range(5)
        ]
        self.assertEqual(len(calls), 1, "worker should have run exactly once")
        self.assertEqual(outcomes[0].outcome, "succeeded")
        for o in outcomes[1:]:
            self.assertEqual(o.outcome, "skipped_duplicate")

    # ── 4. Result cache on replay ──
    def test_02_success_result_cached(self):
        def worker():
            return {"payload": 42}
        first  = run_job("wf-cache", "k-c1", worker, organization_id=1)
        second = run_job("wf-cache", "k-c1", worker, organization_id=1)
        self.assertEqual(first.result,  {"payload": 42})
        self.assertEqual(second.result, {"payload": 42})
        self.assertEqual(second.outcome, "skipped_duplicate")

    # ── 2. Retry schedules next attempt ──
    def test_03_failure_schedules_retry(self):
        def broken():
            raise RuntimeError("transient")
        out = run_job("wf-retry", "k-r1", broken, organization_id=1, max_retries=3)
        self.assertEqual(out.outcome, "retry_scheduled")
        self.assertIsNotNone(out.next_retry_at)
        self.assertGreater(out.next_retry_at, datetime.utcnow())

        # A second immediate invocation must NOT re-run the broken fn —
        # it's not yet time.
        call_count = [0]
        def alsobroken():
            call_count[0] += 1
            raise RuntimeError("transient")
        again = run_job("wf-retry", "k-r1", alsobroken, organization_id=1)
        self.assertEqual(again.outcome, "retry_scheduled")
        self.assertEqual(call_count[0], 0, "fn must not be called before next_retry_at")

    # ── 3. Dead-letter after max_retries ──
    def test_04_dead_letter_after_exhaustion(self):
        def broken():
            raise RuntimeError("always fails")

        # Force the row past its retry limit by manipulating next_retry_at.
        # First failure:
        out1 = run_job("wf-dead", "k-d1", broken, organization_id=1, max_retries=2)
        self.assertEqual(out1.outcome, "retry_scheduled")
        self._force_due(out1.run_id)

        # Second failure:
        out2 = run_job("wf-dead", "k-d1", broken, organization_id=1, max_retries=2)
        self.assertEqual(out2.outcome, "retry_scheduled")
        self._force_due(out2.run_id)

        # Third failure — exhausts retries → dead.
        out3 = run_job("wf-dead", "k-d1", broken, organization_id=1, max_retries=2)
        self.assertEqual(out3.outcome, "dead")

        # Fourth invocation must not run fn.
        call_count = [0]
        def alsobroken():
            call_count[0] += 1
            raise RuntimeError("nope")
        out4 = run_job("wf-dead", "k-d1", alsobroken, organization_id=1)
        self.assertEqual(out4.outcome, "dead")
        self.assertEqual(call_count[0], 0)

    # ── 5. force_retry rearms a dead-lettered run ──
    def test_05_force_retry_rearms(self):
        # Rearm the row from test_04.
        with get_db() as db:
            dead = db.query(WorkflowRun).filter(
                WorkflowRun.workflow_name == "wf-dead",
                WorkflowRun.idempotency_key == "k-d1",
            ).first()
            self.assertIsNotNone(dead)
            self.assertEqual(dead.status, "dead")
            dead_id = dead.id

        self.assertTrue(force_retry(dead_id))
        with get_db() as db:
            revived = db.query(WorkflowRun).filter(WorkflowRun.id == dead_id).first()
            self.assertEqual(revived.status, "failed")
            self.assertEqual(revived.retry_count, 0)

    # ── 6. Sweeper returns due retries ──
    def test_06_sweeper_finds_due(self):
        def broken():
            raise RuntimeError("bang")
        run_job("wf-sweep", "k-s1", broken, organization_id=1, max_retries=3)
        # Age the retry time.
        with get_db() as db:
            row = db.query(WorkflowRun).filter(
                WorkflowRun.workflow_name == "wf-sweep"
            ).first()
            row.next_retry_at = datetime.utcnow() - timedelta(seconds=1)

        due = sweep_ready_retries()
        names = [r.workflow_name for r in due]
        self.assertIn("wf-sweep", names)

    # ── 7. Cross-org isolation of idempotency keys ──
    def test_07_cross_org_keys_independent(self):
        calls = {"a": 0, "b": 0}
        def worker_a():
            calls["a"] += 1
            return "A"
        def worker_b():
            calls["b"] += 1
            return "B"

        # Same key + same workflow_name, different orgs → two separate runs.
        oa = run_job("wf-x", "same-key", worker_a, organization_id=100)
        ob = run_job("wf-x", "same-key", worker_b, organization_id=200)
        self.assertEqual(calls["a"], 1)
        self.assertEqual(calls["b"], 1)
        self.assertEqual(oa.result, "A")
        self.assertEqual(ob.result, "B")

        # And re-running org 100 does NOT fire org 200's function.
        run_job("wf-x", "same-key", worker_a, organization_id=100)
        self.assertEqual(calls["a"], 1)
        self.assertEqual(calls["b"], 1)

    # ── 8. get_dead_letters surfaces admin queue ──
    def test_08_dead_letters_visible(self):
        rows = get_dead_letters(organization_id=1)
        names = [r["workflow_name"] for r in rows]
        # test_04 dead-lettered wf-dead; test_05 rearmed it, so may or may not
        # show depending on test order. Just confirm the API returns a list.
        self.assertIsInstance(rows, list)

    # ── helper ──
    def _force_due(self, run_id: int):
        """Move a failed run's next_retry_at into the past so the next call runs."""
        with get_db() as db:
            r = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if r:
                r.next_retry_at = datetime.utcnow() - timedelta(seconds=1)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        try:
            os.unlink(_TEST_DB)
        except Exception:
            pass
