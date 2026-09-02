"""
Recent-activity feed — derived from existing timestamped CRM records, not a
separate event log. A company's created_at, a contact's created_at, an
outreach row's sent_at/replied_at are already the ground truth for "when did
this happen" — building a parallel activity-log table would just be another
place to keep in sync and another way for the feed to drift from reality.
"""
from __future__ import annotations

from datetime import datetime

from ..database.db import get_db
from ..database.models import Company, Contact, Outreach


def recent_activities(organization_id: int, limit: int = 8) -> list[dict]:
    events: list[dict] = []
    with get_db() as db:
        companies = (
            db.query(Company)
            .filter(Company.organization_id == organization_id)
            .order_by(Company.created_at.desc())
            .limit(limit)
            .all()
        )
        for c in companies:
            if c.created_at:
                events.append({
                    "type": "company_added", "icon": "🏢",
                    "title": c.name, "subtitle": "New company added",
                    "at": c.created_at,
                })

        contacts = (
            db.query(Contact)
            .filter(Contact.organization_id == organization_id)
            .order_by(Contact.created_at.desc())
            .limit(limit)
            .all()
        )
        for ct in contacts:
            if ct.created_at:
                events.append({
                    "type": "contact_added", "icon": "👤",
                    "title": f"{ct.name} added as contact",
                    "subtitle": ct.designation or (ct.company.name if ct.company else ""),
                    "at": ct.created_at,
                })

        outreach = (
            db.query(Outreach)
            .filter(Outreach.organization_id == organization_id)
            .filter(Outreach.sent_at.isnot(None))
            .order_by(Outreach.sent_at.desc())
            .limit(limit)
            .all()
        )
        for o in outreach:
            contact_name = o.contact.name if o.contact else "contact"
            events.append({
                "type": "email_sent", "icon": "📤",
                "title": f"Email sent to {contact_name}",
                "subtitle": (o.subject or "")[:60],
                "at": o.sent_at,
            })
            if o.replied_at:
                events.append({
                    "type": "reply_received", "icon": "↩️",
                    "title": f"Reply received from {contact_name}",
                    "subtitle": "Check the Outreach page",
                    "at": o.replied_at,
                })

    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:limit]


def humanize_delta(dt: datetime) -> str:
    """'2m ago' / '15m ago' / '1h ago' / '3d ago' style relative timestamp."""
    if dt is None:
        return ""
    now = datetime.utcnow()
    seconds = max(0, int((now - dt).total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    return dt.strftime("%b %d")
