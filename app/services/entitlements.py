"""
Plan-based entitlements + quota enforcement (Phase 7).

Central authority for "what is this org allowed to do?" Every expensive
operation calls `check_quota(org_id, feature, amount)` before proceeding.
UI hiding is convenience, not security — enforcement lives here.

Adding a feature:
  1. Add a limit under each plan in `PLAN_LIMITS`.
  2. Add a `_count_<feature>(org_id)` function that returns current usage.
  3. Add the feature name to `_USAGE_COUNTERS`.
  4. Call `check_quota(org_id, "your_feature", 1)` at the enforcement point.

Sentinels:
  -1  → unlimited
   0  → feature disabled for this plan
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Optional

from ..database.db import get_db
from ..database.models import (
    Organization, Company, Contact, Outreach, AILog, OrganizationUser,
    WorkflowRun,
)

log = logging.getLogger(__name__)


# ── Plan matrix ──────────────────────────────────────────────────────────────
# Numbers picked to line up with what's shipped in billing_service.PLANS.
# Change the numbers here — the enforcement points read from this table.
PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free": {
        "companies":              20,
        "contacts":               50,
        "emails_per_day":         10,
        "ai_calls_per_day":       50,
        "ai_tokens_per_day":      50_000,
        "users_per_org":          3,
        "scraping_credits_month": 10,
    },
    "starter": {
        "companies":              500,
        "contacts":               2_000,
        "emails_per_day":         100,
        "ai_calls_per_day":       500,
        "ai_tokens_per_day":      500_000,
        "users_per_org":          5,
        "scraping_credits_month": 200,
    },
    "pro": {
        "companies":              5_000,
        "contacts":               20_000,
        "emails_per_day":         500,
        "ai_calls_per_day":       5_000,
        "ai_tokens_per_day":      5_000_000,
        "users_per_org":          25,
        "scraping_credits_month": 1_000,
    },
    "agency": {  # -1 = unlimited
        "companies":              -1,
        "contacts":               -1,
        "emails_per_day":         -1,
        "ai_calls_per_day":       -1,
        "ai_tokens_per_day":      -1,
        "users_per_org":          -1,
        "scraping_credits_month": -1,
    },
}

DEFAULT_PLAN = "free"


# ── Result contract ──────────────────────────────────────────────────────────

@dataclass
class QuotaResult:
    """
    Never raises for domain outcomes — check .allowed.

    limit=-1  → unlimited
    limit=0   → feature disabled on this plan
    remaining is None when unlimited.
    """
    allowed: bool
    feature: str
    plan: str
    limit: int
    used: int
    remaining: Optional[int]
    reason: str = ""


# ── Public API ───────────────────────────────────────────────────────────────

def get_plan(organization_id: int) -> str:
    """Return the active plan for an org, defaulting to DEFAULT_PLAN."""
    with get_db() as db:
        org = db.query(Organization).filter(
            Organization.id == organization_id
        ).first()
        if not org:
            return DEFAULT_PLAN
        return (org.plan or DEFAULT_PLAN).lower()


def get_limits(organization_id: int) -> dict[str, int]:
    """Return the full limits dict for this org's current plan."""
    plan = get_plan(organization_id)
    return dict(PLAN_LIMITS.get(plan, PLAN_LIMITS[DEFAULT_PLAN]))


def check_quota(organization_id: int, feature: str, amount: int = 1) -> QuotaResult:
    """
    Return a QuotaResult telling the caller whether the operation may proceed.

    Never raises for domain outcomes — call sites should:
        result = check_quota(org_id, "companies")
        if not result.allowed:
            return None  # or user-facing error using result.reason
    """
    plan = get_plan(organization_id)
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS[DEFAULT_PLAN])
    limit = limits.get(feature)
    if limit is None:
        # Undeclared feature — safest default is "deny loudly".
        return QuotaResult(
            allowed=False, feature=feature, plan=plan,
            limit=0, used=0, remaining=0,
            reason=f"feature '{feature}' is not defined in PLAN_LIMITS",
        )

    if limit == -1:
        return QuotaResult(
            allowed=True, feature=feature, plan=plan,
            limit=-1, used=0, remaining=None,
        )
    if limit == 0:
        return QuotaResult(
            allowed=False, feature=feature, plan=plan,
            limit=0, used=0, remaining=0,
            reason=f"'{feature}' is not available on the {plan} plan",
        )

    counter = _USAGE_COUNTERS.get(feature)
    used = counter(organization_id) if counter else 0
    remaining = max(0, limit - used)
    allowed = (used + amount) <= limit
    reason = ""
    if not allowed:
        reason = (
            f"'{feature}' quota exhausted on {plan} plan "
            f"({used}/{limit} used, requested +{amount})"
        )
    return QuotaResult(
        allowed=allowed, feature=feature, plan=plan,
        limit=limit, used=used, remaining=remaining, reason=reason,
    )


def usage_snapshot(organization_id: int) -> dict[str, dict]:
    """Return {feature: {plan, limit, used, remaining}} for every declared feature."""
    plan = get_plan(organization_id)
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS[DEFAULT_PLAN])
    snap: dict[str, dict] = {}
    for feature, limit in limits.items():
        counter = _USAGE_COUNTERS.get(feature)
        used = counter(organization_id) if counter else 0
        snap[feature] = {
            "plan": plan,
            "limit": limit,
            "used": used,
            "remaining": None if limit == -1 else max(0, limit - used),
        }
    return snap


# ── Usage counters ───────────────────────────────────────────────────────────
# One function per feature. All read-only; return an int.

def _count_companies(org_id: int) -> int:
    with get_db() as db:
        return db.query(Company).filter(Company.organization_id == org_id).count()


def _count_contacts(org_id: int) -> int:
    with get_db() as db:
        return db.query(Contact).filter(Contact.organization_id == org_id).count()


def _count_users(org_id: int) -> int:
    with get_db() as db:
        return db.query(OrganizationUser).filter(
            OrganizationUser.organization_id == org_id,
            OrganizationUser.status == "active",
        ).count()


def _count_emails_today(org_id: int) -> int:
    since = datetime.combine(date.today(), datetime.min.time())
    with get_db() as db:
        return (
            db.query(WorkflowRun)
            .filter(WorkflowRun.organization_id == org_id)
            .filter(WorkflowRun.workflow_name.in_(("email_send", "send_followup")))
            .filter(WorkflowRun.status == "succeeded")
            .filter(WorkflowRun.finished_at >= since)
            .count()
        )


def _count_ai_calls_today(org_id: int) -> int:
    since = datetime.combine(date.today(), datetime.min.time())
    with get_db() as db:
        return (
            db.query(AILog)
            .filter(AILog.organization_id == org_id)
            .filter(AILog.status == "ok")
            .filter(AILog.created_at >= since)
            .count()
        )


def _count_ai_tokens_today(org_id: int) -> int:
    since = datetime.combine(date.today(), datetime.min.time())
    with get_db() as db:
        rows = (
            db.query(AILog)
            .filter(AILog.organization_id == org_id)
            .filter(AILog.status == "ok")
            .filter(AILog.created_at >= since)
            .all()
        )
        return sum((r.input_tokens or 0) + (r.output_tokens or 0) for r in rows)


def _count_scraping_credits_month(org_id: int) -> int:
    # Placeholder — no dedicated counter yet. When lead scraping writes its
    # own audit trail (workflow_runs with name='lead_scrape') point this at it.
    return 0


_USAGE_COUNTERS: dict[str, Callable[[int], int]] = {
    "companies":              _count_companies,
    "contacts":               _count_contacts,
    "users_per_org":          _count_users,
    "emails_per_day":         _count_emails_today,
    "ai_calls_per_day":       _count_ai_calls_today,
    "ai_tokens_per_day":      _count_ai_tokens_today,
    "scraping_credits_month": _count_scraping_credits_month,
}
