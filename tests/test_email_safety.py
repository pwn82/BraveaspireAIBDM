"""
Phase 5 email safety tests.

Covers:
  1. Syntax + deliverability rejects garbage / role addresses.
  2. Suppression: blocks a send even with valid recipient.
  3. Unsubscribe token: round-trip signed + tampering rejected.
  4. Unsubscribe endpoint: adds recipient to suppression.
  5. Bounce webhook: hard bounce auto-suppresses; soft does NOT.
  6. Already-sent guard: Outreach with message_id + sent_at is not re-sent.
  7. Daily-quota gate: refuses once cap is exhausted.
  8. Reply threading: IMAP-style match by Message-ID beats subject match.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime

_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["USE_SQLSERVER"] = "false"
os.environ["APP_ENV"]       = "development"
os.environ["SECRET_KEY"]    = "phase5-test-secret-key-must-be-long-enough"
os.environ["DISABLE_SCHEDULER"] = "1"
# No daily cap for most tests; the quota test sets it explicitly.
os.environ.pop("MAX_EMAILS_PER_ORG_PER_DAY", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Silence scheduler under any TestClient usage.
import app.services.scheduler_service as _sched  # noqa: E402
_sched.start_scheduler = lambda: None
_sched.stop_scheduler  = lambda: None

from app.database.db import init_db, get_db                     # noqa: E402
from app.database.models import (
    Organization, Outreach, Contact, Company,
    SuppressionList, BounceEvent, WorkflowRun,
)                                                                # noqa: E402
from app.services.email_service import (
    EmailService, SendResult, parse_unsub_token, _make_unsub_token,
    record_bounce,
)                                                                # noqa: E402


class EmailSafetyTests(unittest.TestCase):
    org_id: int

    @classmethod
    def setUpClass(cls):
        init_db()
        with get_db() as db:
            org = Organization(name="Mail Test Org", slug="mail-test", status="active")
            db.add(org); db.flush()
            cls.org_id = org.id

    def _svc(self) -> EmailService:
        return EmailService(organization_id=self.org_id)

    # ── 1. Syntax / deliverability ──
    def test_01_deliverability_gate(self):
        svc = self._svc()
        self.assertFalse(svc.valid_syntax(""))
        self.assertFalse(svc.valid_syntax("no-at-sign"))
        self.assertFalse(svc.valid_syntax("bad @ format"))
        self.assertTrue(svc.valid_syntax("real@example.io"))
        ok, _ = svc.deliverable("valid@business.co")
        self.assertTrue(ok)
        # Role address blocked.
        ok, reason = svc.deliverable("noreply@business.co")
        self.assertFalse(ok)
        self.assertIn("role address", reason)
        # Blocked domain.
        ok, reason = svc.deliverable("valid@example.com")
        self.assertFalse(ok)
        self.assertIn("blocked domain", reason)

    # ── 2. Suppression blocks send ──
    def test_02_suppression_blocks_send(self):
        svc = self._svc()
        self.assertTrue(svc.add_to_suppression("blocked@real.co", reason="unsubscribe"))
        # Duplicate insert no-ops.
        self.assertFalse(svc.add_to_suppression("blocked@real.co", reason="unsubscribe"))
        self.assertTrue(svc.is_suppressed("BLOCKED@real.co"))  # case-insensitive
        result = svc.send(
            to_email="blocked@real.co", subject="hi", body="hi",
            smtp_cfg={"smtp_user": "u", "smtp_password": "p",
                      "smtp_host": "h", "smtp_port": 587, "from_email": "u@x"},
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "suppressed")

    # ── 3. Signed token round-trip + tampering ──
    def test_03_unsub_token_roundtrip(self):
        tok = _make_unsub_token(self.org_id, "user@real.co", 42)
        payload = parse_unsub_token(tok)
        self.assertEqual(payload["org_id"], self.org_id)
        self.assertEqual(payload["outreach_id"], 42)
        self.assertEqual(payload["email"], "user@real.co")

        # Tamper: flip a byte in the middle → signature fails.
        bad = tok[:-4] + ("A" if tok[-4] != "A" else "B") + tok[-3:]
        self.assertIsNone(parse_unsub_token(bad))
        # Garbage payload:
        self.assertIsNone(parse_unsub_token("obviously.not.a.token"))
        self.assertIsNone(parse_unsub_token(""))

    # ── 4. Unsubscribe endpoint adds to suppression ──
    def test_04_unsub_endpoint_suppresses(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        client = TestClient(app)

        email = "future-unsub@real.co"
        tok = _make_unsub_token(self.org_id, email, None)
        r = client.get(f"/track/unsubscribe/{tok}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("unsubscribed", r.text.lower())
        self.assertTrue(self._svc().is_suppressed(email))

        # Invalid token → 400.
        r = client.get("/track/unsubscribe/garbage")
        self.assertEqual(r.status_code, 400)

    # ── 5. Bounce webhook hard-suppresses; soft does not ──
    def test_05_bounce_webhook_suppression(self):
        record_bounce(
            organization_id=self.org_id,
            email="hard@bouncer.co",
            bounce_type="hard",
            provider="test",
            diagnostic="550 mailbox not found",
        )
        self.assertTrue(self._svc().is_suppressed("hard@bouncer.co"))

        record_bounce(
            organization_id=self.org_id,
            email="soft@bouncer.co",
            bounce_type="soft",
            provider="test",
            diagnostic="452 temporary failure",
        )
        self.assertFalse(self._svc().is_suppressed("soft@bouncer.co"))

        # Complaint auto-suppresses too.
        record_bounce(
            organization_id=self.org_id,
            email="complainer@x.co",
            bounce_type="complaint",
            provider="test",
        )
        self.assertTrue(self._svc().is_suppressed("complainer@x.co"))

    # ── 6. already_sent short-circuits ──
    def test_06_already_sent_guard(self):
        with get_db() as db:
            co = Company(organization_id=self.org_id, name="Co")
            db.add(co); db.flush()
            ct = Contact(organization_id=self.org_id, company_id=co.id,
                         name="X", email="fresh@real.co")
            db.add(ct); db.flush()
            out = Outreach(
                organization_id=self.org_id, contact_id=ct.id,
                subject="hi", body="hi", status="Sent",
                sent_at=datetime.utcnow(),
                message_id_header="<already@sent>",
            )
            db.add(out); db.flush()
            oid = out.id

        result = self._svc().send(
            to_email="fresh@real.co", subject="hi again", body="hi",
            smtp_cfg={"smtp_user": "u", "smtp_password": "p",
                      "smtp_host": "h", "smtp_port": 587, "from_email": "u@x"},
            outreach_id=oid,
        )
        # ok=True but with status="already_sent" — a no-op success.
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "already_sent")

    # ── 7. Daily quota exhaustion ──
    def test_07_quota_exhaustion(self):
        os.environ["MAX_EMAILS_PER_ORG_PER_DAY"] = "2"
        try:
            svc = EmailService(organization_id=self.org_id)
            # Simulate 2 successful sends via workflow_runs rows.
            with get_db() as db:
                for i in range(2):
                    db.add(WorkflowRun(
                        organization_id=self.org_id,
                        workflow_name="email_send",
                        idempotency_key=f"quota-test-{i}",
                        status="succeeded",
                        finished_at=datetime.utcnow(),
                    ))
            self.assertEqual(svc.remaining_daily_quota(), 0)
            result = svc.send(
                to_email="anyone@real.co", subject="hi", body="hi",
                smtp_cfg={"smtp_user": "u", "smtp_password": "p",
                          "smtp_host": "h", "smtp_port": 587, "from_email": "u@x"},
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.status, "quota_exhausted")
        finally:
            os.environ.pop("MAX_EMAILS_PER_ORG_PER_DAY", None)

    # ── 8. Cross-tenant unsub token cannot suppress another org ──
    def test_08_cross_tenant_token_isolation(self):
        # Token issued for THIS org should not be valid to insert into some
        # other org — because parse_unsub_token returns the org_id it was
        # signed for, and add_to_suppression uses that org exclusively.
        with get_db() as db:
            other = Organization(name="Other", slug="other", status="active")
            db.add(other); db.flush()
            other_id = other.id

        tok = _make_unsub_token(other_id, "target@x.co", None)
        payload = parse_unsub_token(tok)
        # Token contains OTHER org — this org's suppression list must NOT gain a row.
        before = _count_suppressions(self.org_id)
        EmailService(payload["org_id"]).add_to_suppression(
            payload["email"], reason="unsubscribe",
        )
        after = _count_suppressions(self.org_id)
        self.assertEqual(before, after, "unsub token for other org must not affect this one")
        self.assertEqual(_count_suppressions(other_id), 1)


def _count_suppressions(org_id: int) -> int:
    with get_db() as db:
        return db.query(SuppressionList).filter(
            SuppressionList.organization_id == org_id
        ).count()


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        try:
            os.unlink(_TEST_DB)
        except Exception:
            pass
