"""
Background scheduler with **durable job storage**.

Phase 4 change: jobs live in the app database via SQLAlchemyJobStore rather
than in-process memory. Restart the API and every scheduled trigger is still
there. Every job body is wrapped in `run_job(...)` so it also inherits
idempotency, retry with backoff, and dead-letter transitions.

For a real distributed queue (Redis + workers), swap the JobStore for a
RedisJobStore or replace this module with a Celery/RQ integration. The
public surface (`start_scheduler`, `stop_scheduler`) stays the same.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, date
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from ..database.db import DATABASE_URL, engine
from .job_service import run_job, sweep_ready_retries
from ..utils.distributed_lock import try_lock

logger = logging.getLogger("scheduler")

_scheduler: Optional[AsyncIOScheduler] = None
_SUPPRESS = os.getenv("DISABLE_SCHEDULER", "").lower() in ("1", "true", "yes")


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        # Reuse the app's engine so we don't open a second pool.
        jobstore = SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")
        _scheduler = AsyncIOScheduler(
            timezone="UTC",
            jobstores={"default": jobstore},
            # coalesce=True: if the scheduler was down and a job "missed" 5 firings,
            # collapse them into one — never the whole backlog.
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        )
    return _scheduler


def start_scheduler():
    if _SUPPRESS:
        logger.info("Scheduler suppressed by DISABLE_SCHEDULER env var.")
        return
    sched = get_scheduler()
    if sched.running:
        return
    # `replace_existing=True` so a code change to the job body / schedule sticks
    # instead of the old serialized job from the DB winning forever.
    sched.add_job(_job_send_followups,      IntervalTrigger(hours=1),     id="send_followups",     replace_existing=True)
    sched.add_job(_job_check_inbox,         IntervalTrigger(minutes=30),  id="check_inbox",        replace_existing=True)
    sched.add_job(_job_analytics_snapshot,  IntervalTrigger(hours=24),    id="analytics_snapshot", replace_existing=True)
    sched.add_job(_job_retry_sweep,         IntervalTrigger(minutes=5),   id="retry_sweep",        replace_existing=True)
    sched.start()
    logger.info("Scheduler started (durable jobstore): send_followups(1h), check_inbox(30m), analytics(24h), retry_sweep(5m).")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# Job bodies — every one runs via run_job() so it's idempotent + retryable.
# These are top-level functions on purpose: SQLAlchemyJobStore pickles the
# reference and needs it to be importable by qualified name.
# ─────────────────────────────────────────────────────────────────────────────

async def _job_send_followups():
    """
    Auto-send follow-ups whose scheduled_at has passed. Idempotent per
    followup id via run_job()'s DB-enforced uniqueness regardless — the
    lock here just stops multiple scheduler replicas from redundantly
    racing the same overdue batch into that constraint every tick.
    """
    with try_lock("scheduler:send_followups", ttl_seconds=120) as acquired:
        if not acquired:
            return
        from ..database.db import get_db
        from ..database.models import FollowUp

        with get_db() as db:
            overdue = (
                db.query(FollowUp)
                .filter(FollowUp.status == "Scheduled",
                        FollowUp.scheduled_at <= datetime.utcnow())
                .all()
            )
            overdue_ids = [f.id for f in overdue]

        sent = 0
        for fu_id in overdue_ids:
            outcome = run_job(
                workflow_name="send_followup",
                idempotency_key=f"followup:{fu_id}",
                fn=_send_one_followup,
                fu_id=fu_id,
            )
            if outcome.outcome == "succeeded":
                sent += 1
        if sent:
            logger.info("[scheduler] Sent %d overdue follow-ups.", sent)


def _send_one_followup(fu_id: int):
    """Send a single follow-up via the Phase 5 safety pipeline. Idempotent."""
    from ..database.db import get_db
    from ..database.models import FollowUp
    from .email_service import EmailService

    with get_db() as db:
        fu = db.query(FollowUp).filter(FollowUp.id == fu_id).first()
        if not fu:
            return {"skipped": "followup gone"}
        if fu.status == "Sent" or fu.sent_at is not None:
            return {"skipped": "already sent"}
        if not (fu.outreach and fu.outreach.contact and fu.outreach.contact.email):
            return {"skipped": "no recipient"}
        recipient   = fu.outreach.contact.email
        subject     = fu.subject or ""
        body        = fu.body or ""
        outreach_id = fu.outreach.id
        org_id      = fu.organization_id or (fu.outreach.organization_id if fu.outreach else None)

    if not org_id:
        # Cannot enforce tenant safety checks — refuse to send.
        raise RuntimeError("follow-up has no organization_id; refusing to send")

    smtp = {
        "smtp_host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port":     int(os.getenv("SMTP_PORT", "587")),
        "smtp_user":     os.getenv("SMTP_USER", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "from_email":    os.getenv("FROM_EMAIL", ""),
        "from_name":     os.getenv("FROM_NAME", "BraveAspire AI BDM"),
    }

    result = EmailService(organization_id=org_id).send(
        to_email=recipient, subject=subject, body=body,
        smtp_cfg=smtp, outreach_id=outreach_id,
    )

    # Terminal-skip statuses should NOT retry — mark the FollowUp and return.
    _TERMINAL_SKIP = {"suppressed", "unsubscribed", "undeliverable", "already_sent"}
    if not result.ok and result.status in _TERMINAL_SKIP:
        with get_db() as db:
            fu = db.query(FollowUp).filter(FollowUp.id == fu_id).first()
            if fu:
                fu.status = f"Skipped:{result.status}"
        return {"skipped": result.status, "reason": result.reason}

    # Retryable failures — raise so run_job() records + schedules a retry.
    if not result.ok:
        raise RuntimeError(f"send failed [{result.status}]: {result.reason}")

    # Success — belt & braces double-write.
    with get_db() as db:
        fu = db.query(FollowUp).filter(FollowUp.id == fu_id).first()
        if fu:
            fu.status = "Sent"
            fu.sent_at = datetime.utcnow()
    return {"recipient": recipient, "message_id": result.message_id,
            "sent_at": datetime.utcnow().isoformat()}


async def _job_check_inbox():
    """Check IMAP inbox for replies and update outreach status."""
    imap_user = os.getenv("IMAP_USER", "")
    imap_pass = os.getenv("IMAP_PASSWORD", "")
    if not imap_user or not imap_pass:
        return
    # This job is naturally idempotent (walks unread mail, marks read on success).
    # Wrapping with run_job would just add a row per tick with no benefit —
    # the lock just avoids two replicas both logging into the same mailbox
    # for the same tick.
    with try_lock("scheduler:check_inbox", ttl_seconds=60) as acquired:
        if not acquired:
            return
        try:
            from .imap_service import IMAPService
            imap = IMAPService(
                host=os.getenv("IMAP_HOST", "imap.gmail.com"),
                port=int(os.getenv("IMAP_PORT", "993")),
                username=imap_user,
                password=imap_pass,
            )
            count = imap.check_replies()
            if count:
                logger.info("[scheduler] Inbox check: %d new replies detected.", count)
        except Exception as e:                                      # noqa: BLE001
            logger.error("[scheduler] check_inbox error: %s", e)


async def _job_analytics_snapshot():
    """One snapshot per active organization. Idempotent per (org, day)."""
    with try_lock("scheduler:analytics_snapshot", ttl_seconds=300) as acquired:
        if not acquired:
            return
        from ..database.db import get_db
        from ..database.models import Organization

        with get_db() as db:
            org_ids = [o.id for o in db.query(Organization).filter(
                Organization.status == "active"
            ).all()]

        today = date.today().isoformat()
        saved = 0
        for org_id in org_ids:
            outcome = run_job(
                workflow_name="analytics_snapshot",
                idempotency_key=f"snap:{today}",
                fn=_snapshot_one_org,
                organization_id=org_id,
                org_id=org_id,
            )
            if outcome.outcome == "succeeded":
                saved += 1
        logger.info("[scheduler] Analytics snapshot saved for %d org(s).", saved)


def _snapshot_one_org(org_id: int):
    from .crm_service import CRMService
    from ..database.db import get_db
    from ..database.models import AILog
    import json as _json

    stats = CRMService(organization_id=org_id).get_pipeline_stats()
    with get_db() as db:
        db.add(AILog(
            organization_id=org_id,
            agent_name="analytics_snapshot",
            task="daily_snapshot",
            result=_json.dumps(stats),
            provider="system",
            model="—",
            duration_ms=0,
        ))
    return stats


async def _job_retry_sweep():
    """Re-dispatch workflow_runs whose next_retry_at has arrived."""
    with try_lock("scheduler:retry_sweep", ttl_seconds=60) as acquired:
        if not acquired:
            return
        _run_retry_sweep()


def _run_retry_sweep():
    ready = sweep_ready_retries()
    if not ready:
        return
    logger.info("[scheduler] Retry sweep: %d ready", len(ready))
    for r in ready:
        # Re-invoke through run_job. The idempotency layer picks the retry
        # branch because the row exists in status="failed".
        # We only know how to re-dispatch the workflows we understand here:
        if r.workflow_name == "send_followup":
            try:
                fu_id = int(r.idempotency_key.split(":", 1)[1])
                run_job(
                    workflow_name=r.workflow_name,
                    idempotency_key=r.idempotency_key,
                    fn=_send_one_followup,
                    fu_id=fu_id,
                )
            except (ValueError, IndexError):
                logger.warning("[scheduler] cannot parse followup id from %r", r.idempotency_key)
        elif r.workflow_name == "analytics_snapshot" and r.organization_id:
            run_job(
                workflow_name=r.workflow_name,
                idempotency_key=r.idempotency_key,
                fn=_snapshot_one_org,
                organization_id=r.organization_id,
                org_id=r.organization_id,
            )
        # Unknown workflows sit until an operator manually retries or removes them.
