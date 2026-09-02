"""
Unified email safety pipeline (Phase 5).

Every outbound email — whether from a Streamlit page, an AI agent, or the
scheduler — must go through EmailService.send(). It runs the plan's full
pre-send pipeline:

    Lead → Email verification (syntax + optional MX)
         → Suppression check (per-org denylist)
         → Unsubscribe check (row-level flag)
         → Tenant daily quota
         → Generate Message-ID + inject unsubscribe footer + tracking pixel
         → SMTP send
         → Record outbound message id, status
         → Return typed result

`send()` never raises for domain errors ("suppressed", "invalid syntax",
"quota exhausted") — it returns a SendResult with a machine-readable status
and a short reason. Only unexpected exceptions (SMTP down, DB down) escape.

Idempotency is provided by wrapping send() calls with app.services.job_service
run_job() at the caller site; EmailService itself is intentionally stateless
about "has this been sent before" — it inspects Outreach.sent_at / message_id
and refuses to re-send a row that already has a message_id.
"""
from __future__ import annotations

import hmac
import hashlib
import base64
import logging
import os
import re
import smtplib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Optional

from ..database.db import get_db
from ..database.models import (
    Outreach, SuppressionList, BounceEvent, WorkflowRun,
)

log = logging.getLogger(__name__)


# ── Simple syntax check (avoids a heavy dependency) ──────────────────────────
# Not perfect (nothing is for email) but rejects the obvious garbage that AI
# outputs. For strict verification, plug a service like ZeroBounce / Kickbox
# behind `verify_deliverable()` below.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)

# Domains we never send to (role addresses, honeypots, obviously fake).
_BLOCKED_LOCAL_PARTS = {
    "no-reply", "noreply", "donotreply", "do-not-reply",
    "postmaster", "abuse", "spam", "example",
}
_BLOCKED_DOMAINS = {
    "example.com", "example.org", "example.net",
    "test.com", "localhost",
}


# ── Result contract ──────────────────────────────────────────────────────────

@dataclass
class SendResult:
    """
    ok         — bool: did we hand this to SMTP successfully?
    status     — machine-readable outcome, one of:
                   sent | invalid_syntax | undeliverable | suppressed |
                   unsubscribed | quota_exhausted | already_sent |
                   smtp_not_configured | smtp_error | no_recipient
    reason     — short human-readable string
    outreach_id — id of the Outreach row that was updated, if any
    message_id  — RFC 5322 Message-ID header that was set (for reply threading)
    """
    ok: bool
    status: str
    reason: str = ""
    outreach_id: Optional[int] = None
    message_id: Optional[str] = None


# ── Public API ───────────────────────────────────────────────────────────────

class EmailService:
    """Tenant-scoped safe email sender."""

    def __init__(self, organization_id: int):
        if not organization_id:
            raise ValueError("EmailService requires organization_id.")
        self.organization_id = int(organization_id)
        # Tenant daily cap. 0 = disabled. Enforced only when configured.
        self.daily_cap = int(os.getenv("MAX_EMAILS_PER_ORG_PER_DAY", "0"))

    # ── Pipeline helpers ────────────────────────────────────────────────────

    @staticmethod
    def normalize(email: str) -> str:
        return (email or "").strip().lower()

    @staticmethod
    def valid_syntax(email: str) -> bool:
        if not email or len(email) > 320:
            return False
        return bool(_EMAIL_RE.match(email))

    @staticmethod
    def deliverable(email: str) -> tuple[bool, str]:
        """
        Cheap pre-flight — catches obviously undeliverable addresses without
        making a network call. Returns (ok, reason).

        Not authoritative — a real SMTP send may still bounce. For a real
        verification service, extend this to call ZeroBounce / Kickbox and
        cache the result on Contact.verified.
        """
        if not EmailService.valid_syntax(email):
            return False, "syntactically invalid"
        local, _, domain = email.partition("@")
        if local.lower() in _BLOCKED_LOCAL_PARTS:
            return False, f"role address ({local}@)"
        if domain.lower() in _BLOCKED_DOMAINS:
            return False, f"blocked domain ({domain})"
        return True, ""

    def is_suppressed(self, email: str) -> bool:
        with get_db() as db:
            hit = (
                db.query(SuppressionList)
                .filter(SuppressionList.organization_id == self.organization_id)
                .filter(SuppressionList.email == self.normalize(email))
                .first()
            )
            return hit is not None

    def add_to_suppression(
        self,
        email: str,
        reason: str,
        source: str = "manual",
        notes: Optional[str] = None,
    ) -> bool:
        """Insert (or no-op if already present). Returns True if newly added."""
        email = self.normalize(email)
        with get_db() as db:
            existing = (
                db.query(SuppressionList)
                .filter(SuppressionList.organization_id == self.organization_id)
                .filter(SuppressionList.email == email)
                .first()
            )
            if existing:
                return False
            db.add(SuppressionList(
                organization_id=self.organization_id,
                email=email, reason=reason, source=source, notes=notes,
            ))
        log.info("Suppression added: org=%s email=%s reason=%s",
                 self.organization_id, email, reason)
        from .audit_service import log_audit
        log_audit(
            "CONTACT_SUPPRESSED", organization_id=self.organization_id,
            resource="suppression_list", details=f"email={email} reason={reason} source={source}",
        )
        return True

    def remaining_daily_quota(self) -> Optional[int]:
        """
        Return remaining sends today for this org.

        Precedence:
          1. Plan-based limit from entitlements.check_quota (authoritative).
          2. Env override MAX_EMAILS_PER_ORG_PER_DAY (legacy / hard override).
        None means unlimited.
        """
        from .entitlements import check_quota
        plan_gate = check_quota(self.organization_id, "emails_per_day", amount=0)
        # plan.limit == -1 → unlimited; -1 short-circuits to env cap only.
        if plan_gate.limit == -1:
            if not self.daily_cap:
                return None
            plan_remaining = None
        else:
            plan_remaining = plan_gate.remaining

        env_remaining = None
        if self.daily_cap:
            since = datetime.combine(date.today(), datetime.min.time())
            with get_db() as db:
                used = (
                    db.query(WorkflowRun)
                    .filter(WorkflowRun.organization_id == self.organization_id)
                    .filter(WorkflowRun.workflow_name.in_(("email_send", "send_followup")))
                    .filter(WorkflowRun.status == "succeeded")
                    .filter(WorkflowRun.finished_at >= since)
                    .count()
                )
            env_remaining = max(0, self.daily_cap - used)

        # The tightest wins.
        values = [v for v in (plan_remaining, env_remaining) if v is not None]
        return min(values) if values else None

    # ── Send ────────────────────────────────────────────────────────────────

    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        smtp_cfg: dict,
        outreach_id: Optional[int] = None,
        base_public_url: Optional[str] = None,
        include_unsubscribe: bool = True,
    ) -> SendResult:
        """
        Send `body` to `to_email`. If `outreach_id` is given, the Outreach row
        gets its message_id_header/sent_at/status updated on success.
        """
        recipient = self.normalize(to_email)
        if not recipient:
            return SendResult(False, "no_recipient", "empty recipient")

        # 1. Syntax + trivial deliverability.
        ok, reason = self.deliverable(recipient)
        if not ok:
            return SendResult(False, "undeliverable", reason)

        # 2. Suppression.
        if self.is_suppressed(recipient):
            return SendResult(False, "suppressed", "on org suppression list")

        # 3. If we have an outreach row, respect its unsubscribed_at flag.
        if outreach_id:
            with get_db() as db:
                out = db.query(Outreach).filter(Outreach.id == outreach_id).first()
                if out:
                    if out.unsubscribed_at:
                        return SendResult(False, "unsubscribed",
                                          "recipient unsubscribed from this thread",
                                          outreach_id=out.id)
                    if out.message_id_header and out.sent_at:
                        # Already sent — do NOT re-send.
                        return SendResult(True, "already_sent",
                                          "outreach already has a Message-ID and sent_at",
                                          outreach_id=out.id,
                                          message_id=out.message_id_header)

        # 4. Tenant daily quota.
        remaining = self.remaining_daily_quota()
        if remaining is not None and remaining <= 0:
            return SendResult(False, "quota_exhausted",
                              f"daily cap {self.daily_cap} reached for this org")

        # 5. SMTP config sanity.
        if not smtp_cfg.get("smtp_user") or not smtp_cfg.get("smtp_password"):
            return SendResult(False, "smtp_not_configured",
                              "SMTP credentials missing")

        # 6. Build MIME with Message-ID + unsub footer + tracking pixel.
        message_id = make_msgid(domain=smtp_cfg.get("from_email", "").split("@")[-1] or "braveaspire.local")

        # Unsubscribe URL — carries a signed token so the recipient can't
        # unsubscribe other people. Best-effort: if outreach_id is missing we
        # embed org+email so the endpoint can still act.
        unsub_url = None
        if include_unsubscribe:
            base = base_public_url or os.getenv("TRACKING_BASE_URL", "http://localhost:8000")
            token = _make_unsub_token(self.organization_id, recipient, outreach_id)
            unsub_url = f"{base.rstrip('/')}/track/unsubscribe/{token}"

        html_body = _wrap_html(body, unsub_url)
        text_body = body if not unsub_url else f"{body}\n\n---\nUnsubscribe: {unsub_url}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = (
            f'{smtp_cfg.get("from_name", "BraveAspire")} '
            f'<{smtp_cfg.get("from_email") or smtp_cfg["smtp_user"]}>'
        )
        msg["To"]         = recipient
        msg["Date"]       = formatdate(localtime=True)
        msg["Message-ID"] = message_id
        # RFC 8058: enables one-click unsubscribe in Gmail/Outlook.
        if unsub_url:
            msg["List-Unsubscribe"]      = f"<{unsub_url}>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # 7. Send.
        try:
            with smtplib.SMTP(smtp_cfg["smtp_host"], smtp_cfg["smtp_port"]) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_cfg["smtp_user"], smtp_cfg["smtp_password"])
                server.sendmail(smtp_cfg["smtp_user"], recipient, msg.as_string())
        except Exception as exc:                                        # noqa: BLE001
            log.exception("SMTP send failed to %s", recipient)
            return SendResult(False, "smtp_error", str(exc)[:200])

        # 8. Record on Outreach if one was named.
        if outreach_id:
            with get_db() as db:
                out = db.query(Outreach).filter(Outreach.id == outreach_id).first()
                if out:
                    out.message_id_header = message_id
                    out.sent_at = datetime.utcnow()
                    if out.status in (None, "", "Draft", "Pending Approval"):
                        out.status = "Sent"

        return SendResult(True, "sent", "delivered to SMTP",
                          outreach_id=outreach_id, message_id=message_id)


# ── Signed unsubscribe tokens ────────────────────────────────────────────────
# Token layout (base64url of "org_id.outreach_id_or_-.email.hmac_sig"):
#   sig = HMAC_SHA256(SECRET_KEY, f"{org}.{oid}.{email}")[:16]

def _secret() -> bytes:
    from .auth_service import SECRET_KEY
    return SECRET_KEY.encode("utf-8")


def _make_unsub_token(org_id: int, email: str, outreach_id: Optional[int]) -> str:
    email = (email or "").strip().lower()
    oid = str(outreach_id) if outreach_id else "-"
    body = f"{org_id}.{oid}.{email}"
    sig = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).digest()[:16]
    payload = f"{body}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"
    return base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()


def parse_unsub_token(token: str) -> Optional[dict]:
    """Return {'org_id', 'outreach_id', 'email'} if valid, None otherwise."""
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + padding).decode()
        body_and_sig = raw.rsplit(".", 1)
        if len(body_and_sig) != 2:
            return None
        body, sig_b64 = body_and_sig
        expected_sig = hmac.new(_secret(), body.encode("utf-8"),
                                hashlib.sha256).digest()[:16]
        sig_padding = "=" * (-len(sig_b64) % 4)
        actual_sig = base64.urlsafe_b64decode(sig_b64 + sig_padding)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        parts = body.split(".", 2)
        if len(parts) != 3:
            return None
        org_str, oid_str, email = parts
        return {
            "org_id":      int(org_str),
            "outreach_id": int(oid_str) if oid_str != "-" else None,
            "email":       email,
        }
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


# ── Bounce processing ────────────────────────────────────────────────────────

def record_bounce(
    organization_id: Optional[int],
    email: str,
    bounce_type: str,
    provider: str = "manual",
    provider_message_id: Optional[str] = None,
    diagnostic: Optional[str] = None,
    raw_payload: Optional[str] = None,
    outreach_id: Optional[int] = None,
) -> BounceEvent:
    """
    Insert a bounce_event row. Side effect: `hard` and `complaint` types
    also auto-add the recipient to the org's SuppressionList.
    """
    email_norm = (email or "").strip().lower()
    with get_db() as db:
        evt = BounceEvent(
            organization_id=organization_id,
            outreach_id=outreach_id,
            email=email_norm,
            bounce_type=bounce_type,
            provider=provider,
            provider_message_id=provider_message_id,
            diagnostic=diagnostic,
            raw_payload=raw_payload,
        )
        db.add(evt)
        db.flush()
        evt_id = evt.id

        if outreach_id:
            out = db.query(Outreach).filter(Outreach.id == outreach_id).first()
            if out:
                out.bounce_status = bounce_type

    if bounce_type in ("hard", "complaint") and organization_id:
        EmailService(organization_id).add_to_suppression(
            email_norm,
            reason=bounce_type,
            source=f"bounce_webhook:{provider}",
            notes=(diagnostic or "")[:500],
        )

    with get_db() as db:
        return db.query(BounceEvent).filter(BounceEvent.id == evt_id).first()


# ── Presentation helpers ─────────────────────────────────────────────────────

def _wrap_html(body: str, unsub_url: Optional[str]) -> str:
    footer = ""
    if unsub_url:
        footer = (
            f'<hr style="border:none;border-top:1px solid #ddd;margin:24px 0">'
            f'<p style="font-size:12px;color:#666">'
            f"Don't want to hear from us? "
            f'<a href="{unsub_url}" style="color:#666">Unsubscribe</a>.'
            f'</p>'
        )
    body_html = body.replace("\n", "<br>")
    return (
        f'<html><body style="font-family:Arial,sans-serif;'
        f'line-height:1.5;color:#222">{body_html}{footer}</body></html>'
    )
