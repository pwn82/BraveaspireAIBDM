"""
Durable background-job execution ledger.

Every important background job (email send, follow-up dispatch, workflow
run) goes through `run_job`. The result:

  • Idempotency  — replaying the same (org, workflow_name, key) triple
    short-circuits with the cached result. Retries, restarts and duplicate
    triggers cannot cause the underlying work to run twice.
  • Retries      — transient failures retry with exponential backoff.
  • Dead-letter  — after `max_retries` failures the row is marked "dead"
    and never runs again. Surface these in an admin queue.
  • Auditing     — every attempt writes started_at / finished_at, last_error
    and retry_count so you can see the reliability picture.

Storage: `workflow_runs` table (Phase 4 migration `0003`).
"""
from __future__ import annotations

import json
import logging
import random
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from ..database.db import get_db
from ..database.models import WorkflowRun

log = logging.getLogger(__name__)


# Exponential backoff schedule (seconds) — index = retry_count AFTER a failure.
# After index len(_BACKOFF) failures, the job is dead-lettered.
_BACKOFF = [60, 300, 1800]  # 1 min, 5 min, 30 min
_JITTER_RATIO = 0.15


def _next_retry_delay(retry_count: int) -> Optional[timedelta]:
    """Delay before attempt N+1, or None if we've exhausted retries."""
    if retry_count >= len(_BACKOFF):
        return None
    base = _BACKOFF[retry_count]
    jitter = base * _JITTER_RATIO
    seconds = base + random.uniform(-jitter, jitter)
    return timedelta(seconds=max(1.0, seconds))


@dataclass
class JobOutcome:
    """What a caller learns about a job run. `outcome` is the source of truth."""
    outcome: str          # "succeeded" | "skipped_duplicate" | "retry_scheduled" | "dead"
    run_id: int
    result: Any = None
    error: Optional[str] = None
    next_retry_at: Optional[datetime] = None


def run_job(
    workflow_name: str,
    idempotency_key: str,
    fn: Callable[..., Any],
    *args,
    organization_id: Optional[int] = None,
    max_retries: int = 3,
    **kwargs,
) -> JobOutcome:
    """
    Idempotent, retry-aware invocation of `fn(*args, **kwargs)`.

    Same (organization_id, workflow_name, idempotency_key) → same outcome.
    A successful past run returns its cached result without re-invoking fn.
    """
    with get_db() as db:
        existing: Optional[WorkflowRun] = (
            db.query(WorkflowRun)
            .filter(
                WorkflowRun.organization_id == organization_id,
                WorkflowRun.workflow_name == workflow_name,
                WorkflowRun.idempotency_key == idempotency_key,
            )
            .first()
        )

        if existing:
            # Already terminal — do NOT run again.
            if existing.status == "succeeded":
                return JobOutcome(
                    outcome="skipped_duplicate",
                    run_id=existing.id,
                    result=_maybe_json_load(existing.result),
                )
            if existing.status == "dead":
                return JobOutcome(
                    outcome="dead",
                    run_id=existing.id,
                    error=existing.last_error,
                )
            # Not yet due for retry — skip this trigger.
            if existing.status == "failed" and existing.next_retry_at and existing.next_retry_at > datetime.utcnow():
                return JobOutcome(
                    outcome="retry_scheduled",
                    run_id=existing.id,
                    error=existing.last_error,
                    next_retry_at=existing.next_retry_at,
                )
            # Currently running (another worker holds it) — refuse to re-enter.
            if existing.status == "running":
                return JobOutcome(
                    outcome="skipped_duplicate",
                    run_id=existing.id,
                    error="already running",
                )
            run = existing
        else:
            run = WorkflowRun(
                organization_id=organization_id,
                workflow_name=workflow_name,
                idempotency_key=idempotency_key,
                status="queued",
                max_retries=max_retries,
            )
            db.add(run)
            db.flush()

        # Take the row into "running" state and commit — that way a crash mid-fn
        # leaves the row in a clear state we can reason about on restart.
        run.status = "running"
        run.started_at = datetime.utcnow()
        db.flush()
        run_id = run.id
        current_retry = run.retry_count or 0

    # ── Execute the actual work OUTSIDE the DB session ────────────────────────
    # A long-running job must not hold a transaction open.
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:                                        # noqa: BLE001
        return _record_failure(run_id, current_retry, exc)

    return _record_success(run_id, result)


def _record_success(run_id: int, result: Any) -> JobOutcome:
    with get_db() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if not run:
            return JobOutcome(outcome="succeeded", run_id=run_id, result=result)
        run.status = "succeeded"
        run.finished_at = datetime.utcnow()
        run.result = _maybe_json_dump(result)
        run.last_error = None
        run.next_retry_at = None
    return JobOutcome(outcome="succeeded", run_id=run_id, result=result)


def _record_failure(run_id: int, current_retry: int, exc: BaseException) -> JobOutcome:
    err = f"{type(exc).__name__}: {exc}"
    tb = traceback.format_exc()
    delay = _next_retry_delay(current_retry)
    with get_db() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if not run:
            return JobOutcome(outcome="dead", run_id=run_id, error=err)
        run.retry_count = (run.retry_count or 0) + 1
        run.last_error = f"{err}\n\n{tb}"
        run.finished_at = datetime.utcnow()
        if delay is None or run.retry_count >= (run.max_retries or 0) + 1:
            run.status = "dead"
            run.next_retry_at = None
            log.error("Job %s (%s) DEAD-LETTERED after %d attempts: %s",
                      run.workflow_name, run.idempotency_key, run.retry_count, err)
            return JobOutcome(outcome="dead", run_id=run_id, error=err)
        run.status = "failed"
        run.next_retry_at = datetime.utcnow() + delay
        log.warning("Job %s (%s) failed attempt %d; retrying at %s",
                    run.workflow_name, run.idempotency_key,
                    run.retry_count, run.next_retry_at)
        return JobOutcome(outcome="retry_scheduled", run_id=run_id, error=err,
                          next_retry_at=run.next_retry_at)


def _maybe_json_dump(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def _maybe_json_load(value: Optional[str]) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


# ── Retry sweeper ────────────────────────────────────────────────────────────

def sweep_ready_retries(now: Optional[datetime] = None) -> list[WorkflowRun]:
    """
    Return workflow_runs whose scheduled retry time has arrived.

    The scheduler calls this periodically and re-dispatches. Because the runs
    are re-invoked through `run_job`, they inherit the idempotency semantics —
    a run already promoted to "succeeded" by another path will not re-execute.
    """
    now = now or datetime.utcnow()
    with get_db() as db:
        rows = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.status == "failed")
            .filter(WorkflowRun.next_retry_at.isnot(None))
            .filter(WorkflowRun.next_retry_at <= now)
            .all()
        )
        # Detach so callers can safely use these after the session closes.
        for r in rows:
            db.expunge(r)
        return rows


def get_dead_letters(organization_id: Optional[int] = None, limit: int = 100) -> list[dict]:
    """Return dead-lettered runs so an admin UI can inspect / retry them."""
    with get_db() as db:
        q = db.query(WorkflowRun).filter(WorkflowRun.status == "dead")
        if organization_id is not None:
            q = q.filter(WorkflowRun.organization_id == organization_id)
        rows = q.order_by(WorkflowRun.finished_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "organization_id": r.organization_id,
                "workflow_name": r.workflow_name,
                "idempotency_key": r.idempotency_key,
                "retry_count": r.retry_count,
                "last_error": (r.last_error or "").splitlines()[0] if r.last_error else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in rows
        ]


def force_retry(run_id: int) -> bool:
    """Manually rearm a dead-lettered run (admin action). Returns True on success."""
    with get_db() as db:
        r = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if not r:
            return False
        r.status = "failed"
        r.retry_count = 0
        r.next_retry_at = datetime.utcnow()
        r.last_error = None
        return True
