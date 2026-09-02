"""
Phase 3 RBAC test suite.

Verifies:
  1. Unit: permissions.PERMISSIONS matrix + has_permission()
  2. Dependency: require_permission() returns 401 / 403 correctly
  3. End-to-end: each role hits each router endpoint; status codes match matrix

Run:  python tests/test_rbac.py
   or python -m pytest tests/test_rbac.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

# Isolate: throwaway SQLite DB, dev SECRET_KEY, no scheduler.
_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["USE_SQLSERVER"] = "false"
os.environ["APP_ENV"]       = "development"
os.environ["SECRET_KEY"]    = "test-secret-key-must-be-long-enough-and-random"

# Path fix.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Silence scheduler during tests (async event-loop tricks under TestClient).
import app.services.scheduler_service as _sched  # noqa: E402
_sched.start_scheduler = lambda: None
_sched.stop_scheduler  = lambda: None

from fastapi.testclient import TestClient       # noqa: E402
from app.database.db import init_db, get_db      # noqa: E402
from app.database.models import (
    User, Organization, OrganizationUser,
)                                                # noqa: E402
from app.services.auth_service import (
    hash_password, create_access_token,
)                                                # noqa: E402
from app.utils.permissions import has_permission, PERMISSIONS  # noqa: E402


# ── Test fixtures — shared org, one user per role ────────────────────────────

def _bootstrap_users() -> dict[str, dict]:
    """Create one active user per role, all in the same org. Returns role→user dict."""
    init_db()
    users: dict[str, dict] = {}
    with get_db() as db:
        org = Organization(name="RBAC Test Org", slug="rbac-test", status="active")
        db.add(org); db.flush()
        for role in ["super_admin", "admin", "sales_manager", "bdm", "sales_executive", "viewer"]:
            u = User(
                email=f"{role}@rbac.test",
                password_hash=hash_password("Password123!"),
                full_name=role.replace("_", " ").title(),
                role=role,
                plan="pro",
                is_active=True,
            )
            db.add(u); db.flush()
            db.add(OrganizationUser(
                organization_id=org.id, user_id=u.id, role=role, status="active",
            ))
            db.flush()
            users[role] = {
                "id": u.id, "email": u.email, "role": role,
                "organization_id": org.id, "mobile": "",
            }
    return users


def _token_for(user_dict: dict) -> str:
    return create_access_token(
        user_id=user_dict["id"],
        email=user_dict["email"],
        role=user_dict["role"],
        mobile=user_dict.get("mobile", ""),
        organization_id=user_dict["organization_id"],
    )


class PermissionCatalogTests(unittest.TestCase):
    """Pure unit tests — no HTTP layer."""

    def test_super_admin_holds_every_permission(self):
        for perm in PERMISSIONS:
            self.assertTrue(
                has_permission({"role": "super_admin"}, perm),
                f"super_admin missing perm '{perm}'",
            )

    def test_viewer_cannot_write(self):
        u = {"role": "viewer"}
        for perm in ("company.create", "company.update", "company.delete",
                     "contact.create", "outreach.create", "outreach.send"):
            self.assertFalse(has_permission(u, perm), f"viewer should not have {perm}")

    def test_none_user_denied_everything(self):
        for perm in PERMISSIONS:
            self.assertFalse(has_permission(None, perm))

    def test_unknown_perm_denied_for_all(self):
        for role in ["super_admin", "admin", "viewer"]:
            self.assertFalse(has_permission({"role": role}, "no.such.perm"))


class EndToEndRBACTests(unittest.TestCase):
    users: dict[str, dict]
    client: TestClient

    @classmethod
    def setUpClass(cls):
        cls.users = _bootstrap_users()
        from backend.main import app
        cls.client = TestClient(app)

    def _auth(self, role: str) -> dict:
        return {"Authorization": f"Bearer {_token_for(self.users[role])}"}

    # ── Auth layer ──
    def test_no_token_returns_401(self):
        r = self.client.get("/api/companies/")
        self.assertEqual(r.status_code, 401)

    def test_bad_token_returns_401(self):
        r = self.client.get("/api/companies/",
                            headers={"Authorization": "Bearer garbage"})
        self.assertEqual(r.status_code, 401)

    # ── Read endpoints: everyone (incl. viewer) succeeds ──
    def test_viewer_can_read_companies(self):
        r = self.client.get("/api/companies/", headers=self._auth("viewer"))
        self.assertEqual(r.status_code, 200)

    def test_viewer_can_read_contacts(self):
        r = self.client.get("/api/contacts/", headers=self._auth("viewer"))
        self.assertEqual(r.status_code, 200)

    def test_viewer_can_read_outreach(self):
        r = self.client.get("/api/outreach/", headers=self._auth("viewer"))
        self.assertEqual(r.status_code, 200)

    # ── Create endpoints: viewer denied, executive+ allowed ──
    def test_viewer_cannot_create_company(self):
        r = self.client.post("/api/companies/", json={"name": "X"},
                             headers=self._auth("viewer"))
        self.assertEqual(r.status_code, 403)

    def test_sales_executive_can_create_company(self):
        r = self.client.post("/api/companies/", json={"name": "Exec-Co"},
                             headers=self._auth("sales_executive"))
        self.assertEqual(r.status_code, 201)

    # ── Delete endpoints: only manager+ allowed ──
    def test_sales_executive_cannot_delete_company(self):
        # Create as admin first, then try to delete as executive.
        c = self.client.post("/api/companies/", json={"name": "Doomed"},
                             headers=self._auth("admin")).json()
        r = self.client.delete(f"/api/companies/{c['id']}",
                               headers=self._auth("sales_executive"))
        self.assertEqual(r.status_code, 403)

    def test_bdm_cannot_delete_company(self):
        c = self.client.post("/api/companies/", json={"name": "AlsoDoomed"},
                             headers=self._auth("admin")).json()
        r = self.client.delete(f"/api/companies/{c['id']}",
                               headers=self._auth("bdm"))
        self.assertEqual(r.status_code, 403)

    def test_sales_manager_can_delete_company(self):
        c = self.client.post("/api/companies/", json={"name": "ForDeletion"},
                             headers=self._auth("admin")).json()
        r = self.client.delete(f"/api/companies/{c['id']}",
                               headers=self._auth("sales_manager"))
        self.assertEqual(r.status_code, 204)

    # ── Admin-only surfaces ──
    def test_bdm_cannot_read_audit_logs(self):
        r = self.client.get("/api/analytics/audit-logs", headers=self._auth("bdm"))
        self.assertEqual(r.status_code, 403)

    def test_admin_can_read_audit_logs(self):
        r = self.client.get("/api/analytics/audit-logs", headers=self._auth("admin"))
        self.assertEqual(r.status_code, 200)

    # ── Analytics: sales_executive lacks analytics.read (per catalog) ──
    def test_sales_executive_denied_analytics(self):
        r = self.client.get("/api/analytics/pipeline",
                            headers=self._auth("sales_executive"))
        self.assertEqual(r.status_code, 403)

    def test_bdm_allowed_analytics(self):
        r = self.client.get("/api/analytics/pipeline", headers=self._auth("bdm"))
        self.assertEqual(r.status_code, 200)

    # ── Security headers land on responses ──
    def test_security_headers_present(self):
        r = self.client.get("/health")
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("Referrer-Policy", r.headers)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        try:
            os.unlink(_TEST_DB)
        except Exception:
            pass
