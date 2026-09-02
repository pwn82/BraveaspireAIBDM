"""
Phase 1 tenant-isolation test.

Creates two organizations (A and B), populates each with companies, contacts,
outreach, and follow-ups, then verifies:

  1. Reads are isolated  — Org A CRMService returns only Org A rows.
  2. Writes are stamped  — new rows carry the caller's organization_id.
  3. Updates are gated   — Org A cannot mutate Org B rows (returns None).
  4. Deletes are gated   — Org A cannot delete Org B rows.
  5. FK smuggling fails  — passing an Org B company_id via Org A returns None.
  6. Stats are isolated  — pipeline counts reflect only the caller's org.

Run:   python -m pytest tests/test_tenant_isolation.py -v
   or:  python tests/test_tenant_isolation.py
"""
from __future__ import annotations
import os
import sys
import tempfile
import unittest
from datetime import datetime

# Force a throwaway SQLite DB for the test — never touch dev/prod.
_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["USE_SQLSERVER"] = "false"
# Force dev mode so SECRET_KEY guard doesn't trip.
os.environ["APP_ENV"] = "development"

# Ensure imports resolve relative to project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import AFTER env vars are set so db.py picks up the test URL.
from app.database.db import init_db, get_db  # noqa: E402
from app.database.models import Organization, OrganizationUser, User  # noqa: E402
from app.services.crm_service import CRMService  # noqa: E402


class TenantIsolationTests(unittest.TestCase):
    org_a_id: int
    org_b_id: int
    crm_a: CRMService
    crm_b: CRMService

    @classmethod
    def setUpClass(cls):
        init_db()  # creates default org + admin
        with get_db() as db:
            org_a = Organization(name="Acme Corp",   slug="acme",   status="active")
            org_b = Organization(name="Beta Labs",   slug="beta",   status="active")
            db.add_all([org_a, org_b]); db.flush()
            cls.org_a_id = org_a.id
            cls.org_b_id = org_b.id
        cls.crm_a = CRMService(organization_id=cls.org_a_id)
        cls.crm_b = CRMService(organization_id=cls.org_b_id)

    # ── 1. Reads are isolated ────────────────────────────────────────────────
    def test_01_reads_isolated(self):
        self.crm_a.add_company({"name": "A-Widgets Inc"})
        self.crm_a.add_company({"name": "A-Gears Co"})
        self.crm_b.add_company({"name": "B-Cogs LLC"})

        names_a = {c["name"] for c in self.crm_a.get_companies()}
        names_b = {c["name"] for c in self.crm_b.get_companies()}
        self.assertEqual(names_a, {"A-Widgets Inc", "A-Gears Co"})
        self.assertEqual(names_b, {"B-Cogs LLC"})
        self.assertFalse(names_a & names_b, "orgs must not share companies")

    # ── 2. Writes are stamped with the caller's org ─────────────────────────
    def test_02_writes_stamped(self):
        created = self.crm_a.add_company({"name": "A-Stamped"})
        self.assertEqual(created["organization_id"], self.org_a_id)

    # ── 3. Updates are gated by org ──────────────────────────────────────────
    def test_03_cross_org_update_denied(self):
        b_row = self.crm_b.add_company({"name": "B-Untouchable"})
        # Org A tries to mutate a row owned by Org B → None (no leak).
        result = self.crm_a.update_company(b_row["id"], {"name": "PWNED"})
        self.assertIsNone(result)
        # Confirm the row was NOT mutated.
        refreshed = self.crm_b.update_company(b_row["id"], {"status": "Checked"})
        self.assertEqual(refreshed["name"], "B-Untouchable")

    # ── 4. Deletes are gated by org ──────────────────────────────────────────
    def test_04_cross_org_delete_denied(self):
        b_row = self.crm_b.add_company({"name": "B-Persistent"})
        self.assertFalse(self.crm_a.delete_company(b_row["id"]))
        # Row still there under Org B.
        still_there = [c["name"] for c in self.crm_b.get_companies()]
        self.assertIn("B-Persistent", still_there)

    # ── 5. Cross-org FK smuggling fails ──────────────────────────────────────
    def test_05_cross_org_fk_smuggle(self):
        # Set up: Org B has a company; Org A tries to attach a contact to it.
        b_co = self.crm_b.add_company({"name": "B-Target"})
        smuggled = self.crm_a.add_contact({
            "company_id": b_co["id"],
            "name": "Sneaky",
            "email": "s@evil.co",
        })
        self.assertIsNone(smuggled, "adding a contact to another org's company must fail")

        # Same trick for outreach.
        b_ct = self.crm_b.add_contact({
            "company_id": b_co["id"], "name": "Legit", "email": "l@b.co",
        })
        self.assertIsNotNone(b_ct)
        bad_out = self.crm_a.create_outreach({
            "contact_id": b_ct["id"], "subject": "hi", "body": "hi",
        })
        self.assertIsNone(bad_out, "creating outreach for another org's contact must fail")

    # ── 6. Analytics stats are org-scoped ────────────────────────────────────
    def test_06_stats_isolated(self):
        # After setup: Org A has 3 companies (A-Widgets, A-Gears, A-Stamped);
        # Org B has 4 (B-Cogs, B-Untouchable, B-Persistent, B-Target).
        stats_a = self.crm_a.get_pipeline_stats()
        stats_b = self.crm_b.get_pipeline_stats()
        self.assertEqual(stats_a["total_companies"], 3)
        self.assertEqual(stats_b["total_companies"], 4)

    # ── 7. Bare CRMService() still refuses to construct ──────────────────────
    def test_07_no_default_construction(self):
        with self.assertRaises(ValueError):
            CRMService()  # must not be allowed

    # ── 8. system=True escape hatch still works for legitimate use ──────────
    def test_08_system_mode_sees_all(self):
        sys_crm = CRMService(system=True)
        all_names = {c["name"] for c in sys_crm.get_companies()}
        # Should see rows from both orgs.
        self.assertIn("A-Widgets Inc", all_names)
        self.assertIn("B-Cogs LLC",   all_names)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        # Best-effort cleanup — Windows may hold the file open briefly.
        try:
            os.unlink(_TEST_DB)
        except Exception:
            pass
