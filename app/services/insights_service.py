"""
Rule-based dashboard insights.

Every insight here is computed directly from real outreach/company/contact
data — never an LLM call, never a canned string. Consistent with this
codebase's outreach-safety principle: an insight only appears when there is
enough underlying data to support it (see MIN_SAMPLE); otherwise it's
silently omitted rather than shown with a guessed or fabricated number.
"""
from __future__ import annotations

from collections import defaultdict

from ..database.db import get_db
from ..database.models import Company, Contact, Outreach

MIN_SAMPLE = 5


def compute_insights(organization_id: int) -> list[dict]:
    with get_db() as db:
        rows = (
            db.query(Outreach, Contact, Company)
            .join(Contact, Outreach.contact_id == Contact.id)
            .outerjoin(Company, Contact.company_id == Company.id)
            .filter(Outreach.organization_id == organization_id)
            .filter(Outreach.sent_at.isnot(None))
            .all()
        )

    insights: list[dict] = []
    insights += _industry_reply_rate_insight(rows)
    insights += _best_sending_time_insight(rows)
    return insights


def _industry_reply_rate_insight(rows) -> list[dict]:
    if len(rows) < MIN_SAMPLE:
        return []

    by_industry = defaultdict(lambda: {"sent": 0, "replied": 0})
    for o, _ct, co in rows:
        industry = (co.industry if co else None) or "Unknown"
        by_industry[industry]["sent"] += 1
        if o.replied_at:
            by_industry[industry]["replied"] += 1

    overall_sent = sum(v["sent"] for v in by_industry.values())
    overall_replied = sum(v["replied"] for v in by_industry.values())
    if not overall_sent:
        return []
    overall_rate = overall_replied / overall_sent

    best_industry, best_stats, best_rate = None, None, overall_rate
    for industry, v in by_industry.items():
        if v["sent"] < MIN_SAMPLE or industry == "Unknown":
            continue
        rate = v["replied"] / v["sent"]
        if rate > best_rate:
            best_industry, best_stats, best_rate = industry, v, rate

    if not best_industry or overall_rate <= 0:
        return []
    lift_pct = round((best_rate - overall_rate) / overall_rate * 100)
    if lift_pct < 10:
        return []

    return [{
        "icon": "📈", "title": "High conversion opportunity",
        "body": (
            f"Leads from the {best_industry} industry have a {lift_pct}% higher reply rate "
            f"({round(best_rate * 100)}% vs {round(overall_rate * 100)}% overall, "
            f"based on {best_stats['sent']} sends). Consider focusing more outreach here."
        ),
        "cta_label": "View Leads", "cta_page": "pages/1_Companies.py",
    }]


def _best_sending_time_insight(rows) -> list[dict]:
    if len(rows) < MIN_SAMPLE * 2:
        return []

    by_hour = defaultdict(lambda: {"sent": 0, "replied": 0})
    for o, _ct, _co in rows:
        hour = o.sent_at.hour
        by_hour[hour]["sent"] += 1
        if o.replied_at:
            by_hour[hour]["replied"] += 1

    best_hour, best_rate, best_sent = None, 0.0, 0
    for hour, v in by_hour.items():
        if v["sent"] < 3:
            continue
        rate = v["replied"] / v["sent"]
        if rate > best_rate:
            best_hour, best_rate, best_sent = hour, rate, v["sent"]

    if best_hour is None or best_rate <= 0:
        return []

    end_hour = (best_hour + 2) % 24
    return [{
        "icon": "⏰", "title": "Best sending time",
        "body": (
            f"Emails sent around {_fmt_hour(best_hour)}–{_fmt_hour(end_hour)} get your highest "
            f"reply rate ({round(best_rate * 100)}%, based on {best_sent} sends)."
        ),
        "cta_label": "View Analytics", "cta_page": "pages/5_Analytics.py",
    }]


def _fmt_hour(h: int) -> str:
    period = "AM" if h < 12 else "PM"
    display = h % 12 or 12
    return f"{display}:00 {period}"
