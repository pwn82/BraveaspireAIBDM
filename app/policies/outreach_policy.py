"""
Central outreach authorization gate (P0 hardening).

Principle from the senior production review: AI can *recommend*; deterministic
code must *authorize*. This module is the one place that decides whether a
given contact is eligible to receive outreach — callers (Streamlit pages,
API routers, the BDM workflow) must call `evaluate_outreach()` before
offering a Send/Approve action, and must respect its verdict.

This does NOT duplicate the send-time checks already enforced inside
`EmailService.send()` (suppression list, unsubscribe flag, already-sent
guard, daily quota) — those remain the authoritative last-mile gate and
still run unconditionally on every send. `evaluate_outreach()` adds the
checks that must happen *before* a send is attempted, chiefly: never send
to a contact whose email address was inferred/guessed rather than sourced
from a real record, unless a human has explicitly promoted it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Contact.email_status values. See app/database/models.py::Contact.
# "inferred"   — AI guessed this address (e.g. firstname@domain pattern).
#                Must NEVER be used for outreach until a human promotes it.
# "bounced"    — a previous send to this address hard-bounced.
# "suppressed" — explicitly blocked (unsubscribe / complaint / manual).
BLOCKED_EMAIL_STATUSES = {"inferred", "bounced", "suppressed"}
# "unknown" (legacy rows, pre-migration) and "unverified" (a human typed it
# into the CRM) are allowed through — human-entered contacts are not
# fabricated data, they just haven't been run through a verification API.
NEEDS_REVIEW_EMAIL_STATUSES = {"unknown", "unverified"}
VERIFIED_EMAIL_STATUS = "verified"


@dataclass
class OutreachDecision:
    allowed: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        return "; ".join(self.blockers) if self.blockers else ""


def evaluate_outreach(
    *,
    organization_id: int,
    contact_email: str,
    contact_email_status: str = "unknown",
    is_approved: bool = True,
    campaign_active: bool = True,
) -> OutreachDecision:
    """
    Pre-send authorization check. Returns allowed=False with concrete
    `blockers` reasons if this outreach must not proceed to EmailService.

    `warnings` are non-blocking — surface them in the UI (e.g. a
    "NEEDS REVIEW" badge) but do not prevent sending.
    """
    blockers: list[str] = []
    warnings: list[str] = []

    email = (contact_email or "").strip()
    if not email:
        blockers.append("no_email")

    status = (contact_email_status or "unknown").strip().lower()
    if status in BLOCKED_EMAIL_STATUSES:
        blockers.append(f"email_{status}")
    elif status in NEEDS_REVIEW_EMAIL_STATUSES:
        warnings.append("email_not_verified")

    if not is_approved:
        blockers.append("approval_required")

    if not campaign_active:
        blockers.append("campaign_inactive")

    if not organization_id:
        blockers.append("no_organization_context")

    return OutreachDecision(allowed=not blockers, blockers=blockers, warnings=warnings)


def badge_for_email_status(status: str) -> str:
    """UI helper — short risk badge text for a contact's email_status."""
    return {
        "verified":   "VERIFIED",
        "unverified": "NEEDS REVIEW",
        "unknown":    "NEEDS REVIEW",
        "inferred":   "AI-GUESSED — BLOCKED",
        "bounced":    "BOUNCED — BLOCKED",
        "suppressed": "SUPPRESSED — BLOCKED",
    }.get((status or "unknown").lower(), "NEEDS REVIEW")
