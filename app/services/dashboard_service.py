"""
Daily trend series for the dashboard's KPI sparklines — computed directly
from existing timestamped records (Company.created_at, Contact.
email_verified_at, Outreach.sent_at/replied_at). No separate snapshot table:
a sparkline is just "count of X per day for the last N days," which these
tables already have everything needed to answer.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..database.db import get_db
from ..database.models import Company, Contact, Outreach


def _daily_counts(dates: list, days: int) -> list[int]:
    today = datetime.utcnow().date()
    buckets = {today - timedelta(days=i): 0 for i in range(days)}
    for dt in dates:
        if dt is None:
            continue
        d = dt.date()
        if d in buckets:
            buckets[d] += 1
    return [buckets[today - timedelta(days=i)] for i in range(days - 1, -1, -1)]


def kpi_sparklines(organization_id: int, days: int = 7) -> dict:
    since = datetime.utcnow() - timedelta(days=days)
    with get_db() as db:
        companies = [
            r[0] for r in db.query(Company.created_at)
            .filter(Company.organization_id == organization_id, Company.created_at >= since)
            .all()
        ]
        verified = [
            r[0] for r in db.query(Contact.email_verified_at)
            .filter(Contact.organization_id == organization_id, Contact.email_verified_at >= since)
            .all()
        ]
        sent = [
            r[0] for r in db.query(Outreach.sent_at)
            .filter(Outreach.organization_id == organization_id, Outreach.sent_at >= since)
            .all()
        ]
        replied = [
            r[0] for r in db.query(Outreach.replied_at)
            .filter(Outreach.organization_id == organization_id, Outreach.replied_at >= since)
            .all()
        ]

    return {
        "companies": _daily_counts(companies, days),
        "verified_contacts": _daily_counts(verified, days),
        "emails_sent": _daily_counts(sent, days),
        "replies": _daily_counts(replied, days),
    }
