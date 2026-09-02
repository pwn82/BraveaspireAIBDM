"""
Phase 8 auth tests — cover the security-critical paths.

Covers:
  1. hash_password produces bcrypt hash; verify_password round-trip.
  2. Successful login returns user dict + no error.
  3. Wrong password returns None + error string.
  4. MAX_FAILED_ATTEMPTS wrong passwords lock the account.
  5. Locked account rejects even correct password.
  6. JWT round-trip: create -> decode returns claims (including org_id).
  7. JWT with wrong secret is rejected.
  8. Expired JWT is rejected.
  9. Refresh-token flow: create -> verify -> revoke -> verify fails.
 10. change_password rehashes correctly.
 11. Inactive user cannot authenticate.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["USE_SQLSERVER"] = "false"
os.environ["APP_ENV"]       = "development"
os.environ["SECRET_KEY"]    = "phase8-auth-test-key-must-be-long-enough"
os.environ["DISABLE_SCHEDULER"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jose import jwt                                             # noqa: E402
from app.database.db import init_db, get_db                      # noqa: E402
from app.database.models import (
    User, Organization, OrganizationUser, RefreshToken,
)                                                                # noqa: E402
from app.services.auth_service import (
    hash_password, verify_password,
    authenticate, create_access_token, decode_access_token,
    create_refresh_token, verify_refresh_token, revoke_refresh_token,
    change_password, get_user_by_id,
    SECRET_KEY, ALGORITHM, MAX_FAILED_ATTEMPTS,
)                                                                # noqa: E402


def _make_user(email: str, password: str, is_active: bool = True) -> int:
    """Create an active user in an org. Returns user id."""
    with get_db() as db:
        # Ensure a default org exists (init_db seeds one, reuse it).
        org = db.query(Organization).first()
        if not org:
            org = Organization(name="Default", slug="default", status="active", plan="free")
            db.add(org); db.flush()
        u = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Test User",
            role="admin",
            is_active=is_active,
        )
        db.add(u); db.flush()
        db.add(OrganizationUser(
            organization_id=org.id, user_id=u.id,
            role="admin", status="active",
        ))
        db.flush()
        return u.id


class PasswordHashTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_hash_and_verify_roundtrip(self):
        h = hash_password("s3cret-pass")
        self.assertTrue(h.startswith("$2"))  # bcrypt marker
        self.assertTrue(verify_password("s3cret-pass", h))
        self.assertFalse(verify_password("wrong-pass", h))

    def test_02_verify_handles_garbage_gracefully(self):
        # Malformed hash must not raise.
        self.assertFalse(verify_password("anything", "not-a-real-hash"))
        self.assertFalse(verify_password("", ""))


class AuthenticationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_03_login_success(self):
        _make_user("good@auth.test", "CorrectPassw0rd!")
        user, err = authenticate("good@auth.test", "CorrectPassw0rd!")
        self.assertIsNotNone(user)
        self.assertEqual(err, "")
        self.assertEqual(user["email"], "good@auth.test")
        self.assertIn("organization_id", user)

    def test_04_login_wrong_password(self):
        _make_user("wrong@auth.test", "CorrectPassw0rd!")
        user, err = authenticate("wrong@auth.test", "WrongPassword!")
        self.assertIsNone(user)
        self.assertTrue(err)  # some non-empty message

    def test_05_login_nonexistent_email(self):
        user, err = authenticate("noone@auth.test", "AnyThing123!")
        self.assertIsNone(user)
        # Message must NOT reveal whether the email exists.
        self.assertIn("Invalid", err)

    def test_06_lockout_after_max_failed_attempts(self):
        _make_user("lockme@auth.test", "CorrectPassw0rd!")
        for _ in range(MAX_FAILED_ATTEMPTS):
            authenticate("lockme@auth.test", "WrongPassword!")
        # Even the correct password now fails — user is locked.
        user, err = authenticate("lockme@auth.test", "CorrectPassw0rd!")
        self.assertIsNone(user)
        self.assertIn("lock", err.lower())

    def test_07_inactive_user_denied(self):
        _make_user("inactive@auth.test", "CorrectPassw0rd!", is_active=False)
        user, err = authenticate("inactive@auth.test", "CorrectPassw0rd!")
        self.assertIsNone(user)


class JWTTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_08_jwt_roundtrip_carries_org_id(self):
        uid = _make_user("jwt@auth.test", "CorrectPassw0rd!")
        tok = create_access_token(user_id=uid, email="jwt@auth.test",
                                  role="admin", mobile="", organization_id=1)
        claims = decode_access_token(tok)
        self.assertIsNotNone(claims)
        self.assertEqual(claims["sub"], str(uid))
        self.assertEqual(claims["email"], "jwt@auth.test")
        self.assertEqual(claims["role"], "admin")
        self.assertEqual(claims["org"], 1)
        self.assertEqual(claims["type"], "access")

    def test_09_jwt_wrong_secret_rejected(self):
        uid = _make_user("jwt-wrong@auth.test", "CorrectPassw0rd!")
        # Forge a token with a different key.
        payload = {
            "sub":  str(uid),
            "email":"jwt-wrong@auth.test",
            "role": "admin",
            "type": "access",
            "exp":  datetime.utcnow() + timedelta(hours=1),
        }
        forged = jwt.encode(payload, "other-secret", algorithm=ALGORITHM)
        self.assertIsNone(decode_access_token(forged))

    def test_10_expired_jwt_rejected(self):
        payload = {
            "sub":  "1",
            "email":"expired@auth.test",
            "role": "admin",
            "type": "access",
            "exp":  datetime.utcnow() - timedelta(seconds=1),   # already expired
        }
        expired = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        self.assertIsNone(decode_access_token(expired))

    def test_11_wrong_token_type_rejected(self):
        # A "refresh" claim in an access-token slot must be refused.
        payload = {
            "sub":  "1",
            "email":"typemix@auth.test",
            "role": "admin",
            "type": "refresh",
            "exp":  datetime.utcnow() + timedelta(hours=1),
        }
        tok = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        self.assertIsNone(decode_access_token(tok))


class RefreshTokenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_12_refresh_roundtrip_and_revoke(self):
        uid = _make_user("refresh@auth.test", "CorrectPassw0rd!")
        raw = create_refresh_token(uid, device_hint="pytest")
        self.assertTrue(raw)
        # Verify returns the user dict (same shape as authenticate()).
        info = verify_refresh_token(raw)
        self.assertIsNotNone(info)
        self.assertEqual(info["id"], uid)
        self.assertEqual(info["email"], "refresh@auth.test")

        # Confirm the DB row exists.
        with get_db() as db:
            n = db.query(RefreshToken).filter(RefreshToken.user_id == uid).count()
            self.assertGreaterEqual(n, 1)

        # Revoke, then verify fails.
        revoke_refresh_token(raw)
        self.assertIsNone(verify_refresh_token(raw))


class PasswordChangeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_13_change_password_rehashes(self):
        uid = _make_user("pwchange@auth.test", "OldPassw0rd!")
        # Old password works.
        user, err = authenticate("pwchange@auth.test", "OldPassw0rd!")
        self.assertIsNotNone(user)

        ok, msg = change_password(uid, "NewPassw0rd!")
        self.assertTrue(ok, msg)

        # Old password no longer works; new one does.
        user, err = authenticate("pwchange@auth.test", "OldPassw0rd!")
        self.assertIsNone(user)
        user, err = authenticate("pwchange@auth.test", "NewPassw0rd!")
        self.assertIsNotNone(user)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        try:
            os.unlink(_TEST_DB)
        except Exception:
            pass
