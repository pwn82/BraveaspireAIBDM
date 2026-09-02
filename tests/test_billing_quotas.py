"""
Phase 7 billing + quota tests.

Covers:
  1. `get_plan` defaults to "free".
  2. `check_quota` reports allowed/limit/used correctly for a fresh org.
  3. Free plan blocks the 21st company at CRMService.add_company.
  4. Upgrading to `pro` raises the limit; the next add_company succeeds.
  5. Agency plan (-1 sentinel) returns unlimited.
  6. Unknown feature is denied loudly (fail-safe).
  7. Stripe webhook is idempotent — replay never inserts a duplicate.
  8. Stripe checkout.completed sets Organization.plan (via metadata).
  9. Subscription cancellation downgrades org back to "free".
 10. `usage_snapshot` returns every declared feature with correct shape.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["USE_SQLSERVER"] = "false"
os.environ["APP_ENV"]       = "development"
os.environ["DISABLE_SCHEDULER"] = "1"
# Ensure Stripe webhook takes the unsigned-dev path.
os.environ.pop("STRIPE_WEBHOOK_SECRET", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.db import init_db, get_db                    # noqa: E402
from app.database.models import (
    Organization, OrganizationUser, User, Subscription, StripeEvent,
)                                                              # noqa: E402
from app.services.crm_service import CRMService                # noqa: E402
from app.services.entitlements import (
    check_quota, get_plan, get_limits, usage_snapshot, PLAN_LIMITS,
)                                                              # noqa: E402
from app.services.auth_service import hash_password            # noqa: E402
from app.services.billing_service import handle_webhook        # noqa: E402


def _new_org(slug: str, plan: str = "free", with_user_email: str = None) -> int:
    with get_db() as db:
        org = Organization(name=f"Org {slug}", slug=slug, status="active", plan=plan)
        db.add(org); db.flush()
        oid = org.id
        if with_user_email:
            u = User(
                email=with_user_email,
                password_hash=hash_password("Password123!"),
                full_name="tester",
                role="admin",
                is_active=True,
            )
            db.add(u); db.flush()
            db.add(OrganizationUser(
                organization_id=oid, user_id=u.id,
                role="admin", status="active",
            ))
    return oid


class EntitlementTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_default_plan_is_free(self):
        oid = _new_org("default-plan-org")
        self.assertEqual(get_plan(oid), "free")

    def test_02_check_quota_returns_correct_shape(self):
        oid = _new_org("shape-org")
        r = check_quota(oid, "companies", amount=1)
        self.assertTrue(r.allowed)
        self.assertEqual(r.plan, "free")
        self.assertEqual(r.limit, PLAN_LIMITS["free"]["companies"])
        self.assertEqual(r.used, 0)
        self.assertEqual(r.remaining, r.limit)

    def test_03_free_plan_blocks_over_cap(self):
        oid  = _new_org("cap-org")
        crm  = CRMService(organization_id=oid)
        cap  = PLAN_LIMITS["free"]["companies"]
        # Fill the free plan cap.
        for i in range(cap):
            row = crm.add_company({"name": f"Co-{i}"})
            self.assertIsNotNone(row, f"add_company #{i+1} should succeed")
        # The (cap+1)-th add must return None.
        blocked = crm.add_company({"name": "OverCap"})
        self.assertIsNone(blocked, "cap+1 company must be blocked")
        # And check_quota reports it clearly.
        r = check_quota(oid, "companies", amount=1)
        self.assertFalse(r.allowed)
        self.assertEqual(r.used, cap)
        self.assertEqual(r.remaining, 0)
        self.assertIn("quota exhausted", r.reason.lower())

    def test_04_upgrade_raises_limit(self):
        oid = _new_org("upgrade-org")
        crm = CRMService(organization_id=oid)
        for i in range(PLAN_LIMITS["free"]["companies"]):
            crm.add_company({"name": f"c{i}"})
        self.assertIsNone(crm.add_company({"name": "over"}))

        # Upgrade plan directly (webhook test below covers Stripe path).
        with get_db() as db:
            db.query(Organization).filter(Organization.id == oid).update({"plan": "pro"})

        row = crm.add_company({"name": "after-upgrade"})
        self.assertIsNotNone(row, "add_company after upgrade should succeed")

    def test_05_agency_is_unlimited(self):
        oid = _new_org("agency-org", plan="agency")
        r = check_quota(oid, "companies", amount=1)
        self.assertTrue(r.allowed)
        self.assertEqual(r.limit, -1)
        self.assertIsNone(r.remaining)

    def test_06_unknown_feature_denied_loudly(self):
        oid = _new_org("unknown-feature-org")
        r = check_quota(oid, "no.such.feature", amount=1)
        self.assertFalse(r.allowed)
        self.assertIn("not defined", r.reason)

    def test_07_usage_snapshot_shape(self):
        oid = _new_org("snapshot-org")
        snap = usage_snapshot(oid)
        for feature in PLAN_LIMITS["free"]:
            self.assertIn(feature, snap)
            self.assertIn("used",      snap[feature])
            self.assertIn("limit",     snap[feature])
            self.assertIn("plan",      snap[feature])
            self.assertIn("remaining", snap[feature])


class StripeWebhookTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_08_webhook_is_idempotent(self):
        oid = _new_org("webhook-idem-org", with_user_email="wh-idem@x.co")
        event = self._checkout_event("evt_test_idem_1", oid, "wh-idem@x.co", "starter")

        payload = json.dumps(event).encode("utf-8")
        r1 = handle_webhook(payload, sig_header="")
        r2 = handle_webhook(payload, sig_header="")
        r3 = handle_webhook(payload, sig_header="")

        self.assertEqual(r1.get("status"), "ok")
        self.assertFalse(r1.get("idempotent"), "first delivery should not be marked idempotent")
        self.assertTrue(r2.get("idempotent"), "second delivery must short-circuit")
        self.assertTrue(r3.get("idempotent"))

        # Exactly one stripe_events row for that event_id.
        with get_db() as db:
            n = db.query(StripeEvent).filter(
                StripeEvent.event_id == "evt_test_idem_1"
            ).count()
            self.assertEqual(n, 1)

    def test_09_checkout_sets_plan_from_metadata(self):
        oid = _new_org("webhook-meta-org", with_user_email="wh-meta@x.co")
        event = self._checkout_event("evt_test_meta_1", oid, "wh-meta@x.co", "pro")
        payload = json.dumps(event).encode("utf-8")
        r = handle_webhook(payload, sig_header="")
        self.assertEqual(r["status"], "ok")

        with get_db() as db:
            org = db.query(Organization).filter(Organization.id == oid).first()
            self.assertEqual(org.plan, "pro")
            sub = db.query(Subscription).filter(Subscription.organization_id == oid).first()
            self.assertIsNotNone(sub)
            self.assertEqual(sub.plan, "pro")
            self.assertEqual(sub.status, "active")

    def test_10_subscription_deleted_downgrades_org(self):
        oid = _new_org("webhook-cancel-org", with_user_email="wh-cancel@x.co")
        # First activate.
        activate = self._checkout_event("evt_test_cancel_setup", oid,
                                        "wh-cancel@x.co", "agency",
                                        subscription_id="sub_cancel_1")
        handle_webhook(json.dumps(activate).encode(), sig_header="")
        with get_db() as db:
            self.assertEqual(
                db.query(Organization).filter(Organization.id == oid).first().plan,
                "agency",
            )
        # Now cancel.
        cancel_event = {
            "id":   "evt_test_cancel_run",
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_cancel_1", "status": "canceled"}},
        }
        r = handle_webhook(json.dumps(cancel_event).encode(), sig_header="")
        self.assertEqual(r["status"], "ok")
        with get_db() as db:
            org = db.query(Organization).filter(Organization.id == oid).first()
            self.assertEqual(org.plan, "free", "cancellation must downgrade org to free")

    def _checkout_event(self, event_id: str, org_id: int, email: str, plan: str,
                        subscription_id: str = None) -> dict:
        sub_id = subscription_id or f"sub_{event_id}"
        return {
            "id":   event_id,
            "type": "checkout.session.completed",
            "data": {"object": {
                "id":             f"cs_{event_id}",
                "customer":       f"cus_{event_id}",
                "customer_email": email,
                "subscription":   sub_id,
                "metadata":       {"plan": plan, "organization_id": str(org_id)},
            }},
        }


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        try:
            os.unlink(_TEST_DB)
        except Exception:
            pass
