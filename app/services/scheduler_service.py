"""
Background scheduler — runs inside FastAPI lifespan.
Jobs:
  • every 1 h  : send overdue follow-ups
  • every 30 m : check inbox for replies
  • every 24 h : snapshot analytics
"""
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("scheduler")
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def start_scheduler():
    sched = get_scheduler()
    if sched.running:
        return

    sched.add_job(_job_send_followups,   IntervalTrigger(hours=1),   id="send_followups",   replace_existing=True)
    sched.add_job(_job_check_inbox,      IntervalTrigger(minutes=30),id="check_inbox",      replace_existing=True)
    sched.add_job(_job_analytics_snapshot,IntervalTrigger(hours=24), id="analytics_snapshot",replace_existing=True)
    sched.start()
    logger.info("Scheduler started: send_followups(1h), check_inbox(30m), analytics(24h)")


def stop_scheduler():
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        logger.info("Scheduler stopped.")


# ── Job implementations ───────────────────────────────────────────────────────

async def _job_send_followups():
    """Auto-send follow-ups whose scheduled_at has passed."""
    try:
        from ..database.db import get_db
        from ..database.models import FollowUp, Outreach, Contact
        from ..utils.helpers import send_email as _send

        with get_db() as db:
            overdue = (
                db.query(FollowUp)
                .filter(FollowUp.status == "Scheduled",
                        FollowUp.scheduled_at <= datetime.utcnow())
                .all()
            )
            sent_count = 0
            for fu in overdue:
                if fu.outreach and fu.outreach.contact:
                    contact = fu.outreach.contact
                    # Attempt to pull SMTP settings from env
                    import os
                    smtp = {
                        "smtp_host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
                        "smtp_port":     int(os.getenv("SMTP_PORT", "587")),
                        "smtp_user":     os.getenv("SMTP_USER", ""),
                        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
                        "from_email":    os.getenv("FROM_EMAIL", ""),
                        "from_name":     os.getenv("FROM_NAME", "BraveAspire AI BDM"),
                    }
                    if not smtp["smtp_user"]:
                        break  # SMTP not configured
                    ok, msg = _send(contact.email, fu.subject or "", fu.body or "", smtp)
                    if ok:
                        fu.status   = "Sent"
                        fu.sent_at  = datetime.utcnow()
                        sent_count += 1
            if sent_count:
                logger.info(f"[scheduler] Sent {sent_count} overdue follow-ups.")
    except Exception as e:
        logger.error(f"[scheduler] send_followups error: {e}")


async def _job_check_inbox():
    """Check IMAP inbox for replies and update outreach status."""
    try:
        import os
        imap_user = os.getenv("IMAP_USER", "")
        imap_pass = os.getenv("IMAP_PASSWORD", "")
        if not imap_user or not imap_pass:
            return
        from .imap_service import IMAPService
        imap = IMAPService(
            host=os.getenv("IMAP_HOST", "imap.gmail.com"),
            port=int(os.getenv("IMAP_PORT", "993")),
            username=imap_user,
            password=imap_pass,
        )
        count = imap.check_replies()
        if count:
            logger.info(f"[scheduler] Inbox check: {count} new replies detected.")
    except Exception as e:
        logger.error(f"[scheduler] check_inbox error: {e}")


async def _job_analytics_snapshot():
    """Log a daily analytics snapshot to ai_logs."""
    try:
        from ..services.crm_service import CRMService
        from ..database.db import get_db
        from ..database.models import AILog
        import json

        crm   = CRMService()
        stats = crm.get_pipeline_stats()
        with get_db() as db:
            db.add(AILog(
                agent_name="analytics_snapshot",
                task="daily_snapshot",
                result=json.dumps(stats),
                provider="system",
                model="—",
                duration_ms=0,
            ))
        logger.info("[scheduler] Daily analytics snapshot saved.")
    except Exception as e:
        logger.error(f"[scheduler] analytics_snapshot error: {e}")
