"""
Phase 8 tracking endpoint tests.

Covers:
  1. /track/open/{id} returns a 1×1 GIF with no-store cache header.
  2. Open increments the counter on the matched Outreach row.
  3. Sending an open moves status Sent → Opened + sets opened_at.
  4. Multiple opens increment counter (unique_opens is a separate metric).
  5. /track/click/{id} redirects to the requested URL + increments click_count.
  6. /track/click rejects `javascript:` URLs (open-redirect fix in P3).
  7. /track/click rejects a plain path (must have scheme).
  8. Unknown tracking_id — endpoint stays 200 (avoid recon signal).
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
os.environ["SECRET_KEY"]    = "phase8-tracking-test-secret-key-must-be-long"
os.environ["DISABLE_SCHEDULER"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Silence scheduler.
import app.services.scheduler_service as _sched  # noqa: E402
_sched.start_scheduler = lambda: None
_sched.stop_scheduler  = lambda: None

from fastapi.testclient import TestClient                         # noqa: E402
from app.database.db import init_db, get_db                       # noqa: E402
from app.database.models import (
    Organization, Company, Contact, Outreach,
)                                                                 # noqa: E402
from app.services.email_tracking_service import TRANSPARENT_GIF   # noqa: E402


class TrackingEndpointTests(unittest.TestCase):
    client: TestClient
    tracking_id: str
    outreach_id: int

    @classmethod
    def setUpClass(cls):
        init_db()
        with get_db() as db:
            org = db.query(Organization).first()
            org_id = org.id
            co = Company(organization_id=org_id, name="Track Co")
            db.add(co); db.flush()
            ct = Contact(organization_id=org_id, company_id=co.id,
                         name="Track Contact", email="t@track.co")
            db.add(ct); db.flush()
            out = Outreach(
                organization_id=org_id, contact_id=ct.id,
                subject="hi", body="hi",
                status="Sent", sent_at=datetime.utcnow(),
                tracking_id="track-test-uuid-0001",
            )
            db.add(out); db.flush()
            cls.tracking_id = out.tracking_id
            cls.outreach_id = out.id

        from backend.main import app
        cls.client = TestClient(app)

    def _get_row(self) -> dict:
        """Snapshot the Outreach row into a plain dict — safe after session close."""
        with get_db() as db:
            row = db.query(Outreach).filter(Outreach.id == self.outreach_id).first()
            return {
                "id":          row.id,
                "status":      row.status,
                "open_count":  row.open_count or 0,
                "click_count": row.click_count or 0,
                "opened_at":   row.opened_at,
                "sent_at":     row.sent_at,
            }

    # ── 1 + 2 + 3. Pixel returns GIF, counter increments, status transitions ──
    def test_01_open_pixel(self):
        r = self.client.get(f"/track/open/{self.tracking_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("content-type"), "image/gif")
        self.assertEqual(r.content, TRANSPARENT_GIF)
        self.assertIn("no-store", r.headers.get("cache-control", ""))

        row = self._get_row()
        self.assertEqual(row["open_count"], 1)
        self.assertEqual(row["status"], "Opened")
        self.assertIsNotNone(row["opened_at"])

    def test_02_second_open_increments_counter_only(self):
        # Prior test already opened once.
        before = self._get_row()
        prev_count = before["open_count"]
        prev_opened_at = before["opened_at"]
        r = self.client.get(f"/track/open/{self.tracking_id}")
        self.assertEqual(r.status_code, 200)
        row = self._get_row()
        self.assertEqual(row["open_count"], prev_count + 1)
        # opened_at is set only on first Sent→Opened transition.
        self.assertEqual(row["opened_at"], prev_opened_at)

    # ── 5. Click redirect increments click_count ──
    def test_03_click_redirect(self):
        r = self.client.get(
            f"/track/click/{self.tracking_id}",
            params={"redirect_url": "https://example.com/pricing"},
            follow_redirects=False,
        )
        self.assertIn(r.status_code, (302, 307))
        self.assertEqual(r.headers.get("location"), "https://example.com/pricing")
        row = self._get_row()
        self.assertEqual(row["click_count"], 1)

    # ── 6 + 7. javascript: / bare-path URLs get replaced with the safe default ──
    def test_04_click_rejects_javascript_url(self):
        r = self.client.get(
            f"/track/click/{self.tracking_id}",
            params={"redirect_url": "javascript:alert(1)"},
            follow_redirects=False,
        )
        self.assertIn(r.status_code, (302, 307))
        loc = r.headers.get("location", "")
        self.assertFalse(loc.startswith("javascript:"),
                         "must never redirect to javascript: URL")

    def test_05_click_rejects_scheme_less_url(self):
        r = self.client.get(
            f"/track/click/{self.tracking_id}",
            params={"redirect_url": "/etc/passwd"},
            follow_redirects=False,
        )
        loc = r.headers.get("location", "")
        self.assertTrue(loc.startswith("http://") or loc.startswith("https://"))
        self.assertNotIn("/etc/passwd", loc)

    # ── 8. Unknown tracking id — endpoint returns 200 (no recon) ──
    def test_06_unknown_open_id_stays_quiet(self):
        r = self.client.get("/track/open/does-not-exist-uuid")
        self.assertEqual(r.status_code, 200)
        # Still returns a GIF so scrapers can't fingerprint hits vs misses.
        self.assertEqual(r.headers.get("content-type"), "image/gif")


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        try:
            os.unlink(_TEST_DB)
        except Exception:
            pass
