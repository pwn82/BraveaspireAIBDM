"""
Auth Service
============
Provides:
  • Password hashing / verification (bcrypt)
  • JWT access tokens  (1-hour lifetime)
  • JWT refresh tokens (7-day lifetime, stored as SHA-256 hash)
  • OTP-based login    (mobile as username)
  • TOTP second factor (authenticator app)
  • Account lockout    (5 failed attempts → 15-minute lockout)
  • Admin-only user creation with temp password + email notification
  • RBAC helpers (delegates to app.utils.rbac)
"""

import os
import secrets
import hashlib
import logging
import smtplib
from datetime import datetime, timedelta
from typing import Optional, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import bcrypt as _bcrypt
from jose import JWTError, jwt

from ..database.db import get_db
from ..database.models import User, AuditLog, RefreshToken, OTPCode

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY              = os.getenv("SECRET_KEY", "braveaspire-change-in-production-xyz123")
ALGORITHM               = "HS256"
ACCESS_TOKEN_EXPIRE_H   = 1        # 1 hour
REFRESH_TOKEN_EXPIRE_D  = 7        # 7 days
MAX_FAILED_ATTEMPTS     = 5
LOCKOUT_MINUTES         = 15

PLAN_LIMITS = {
    "free":    {"companies": 20,   "emails_per_day": 10,  "ai_calls": 50},
    "starter": {"companies": 500,  "emails_per_day": 100, "ai_calls": 500},
    "pro":     {"companies": 5000, "emails_per_day": 500, "ai_calls": 5000},
    "agency":  {"companies": -1,   "emails_per_day": -1,  "ai_calls": -1},
}


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT Access Token ──────────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str, role: str, mobile: str = "") -> str:
    payload = {
        "sub":    str(user_id),
        "email":  email,
        "mobile": mobile or "",
        "role":   role,
        "type":   "access",
        "exp":    datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_H),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if data.get("type") != "access":
            return None
        return data
    except JWTError:
        return None


# Keep legacy alias used elsewhere in codebase
def create_token(user_id: int, email: str, role: str) -> str:
    return create_access_token(user_id, email, role)


def decode_token(token: str) -> Optional[dict]:
    return decode_access_token(token)


# ── Refresh Token ─────────────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_refresh_token(user_id: int, device_hint: str = "") -> str:
    """Create a refresh token, store its hash in DB, return the raw token."""
    raw     = secrets.token_urlsafe(64)
    hashed  = _hash_token(raw)
    expires = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_D)
    with get_db() as db:
        db.add(RefreshToken(
            user_id=user_id,
            token_hash=hashed,
            device_hint=device_hint[:200] if device_hint else "",
            expires_at=expires,
        ))
    return raw


def verify_refresh_token(raw_token: str) -> Optional[dict]:
    """Validate a refresh token and return the user dict, or None."""
    hashed = _hash_token(raw_token)
    with get_db() as db:
        rt = db.query(RefreshToken).filter(
            RefreshToken.token_hash == hashed,
            RefreshToken.revoked    == False,
            RefreshToken.expires_at >  datetime.utcnow(),
        ).first()
        if not rt:
            return None
        user = db.query(User).filter(User.id == rt.user_id, User.is_active == True).first()
        if not user:
            return None
        rt.last_used = datetime.utcnow()
        return _user_dict(user)


def revoke_refresh_token(raw_token: str):
    hashed = _hash_token(raw_token)
    with get_db() as db:
        rt = db.query(RefreshToken).filter(RefreshToken.token_hash == hashed).first()
        if rt:
            rt.revoked = True


def revoke_all_refresh_tokens(user_id: int):
    with get_db() as db:
        db.query(RefreshToken).filter(RefreshToken.user_id == user_id).update({"revoked": True})


# ── Lockout helpers ───────────────────────────────────────────────────────────

def _is_locked(user: User) -> bool:
    if user.lockout_until and user.lockout_until > datetime.utcnow():
        return True
    return False


def _record_failed_login(db, user: User):
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        user.lockout_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        log.warning("Account locked: %s (too many failures)", user.email or user.mobile)


def _reset_failed_login(db, user: User):
    user.failed_login_attempts = 0
    user.lockout_until = None


# ── OTP-Based Authentication (primary flow) ───────────────────────────────────

def get_user_by_mobile(mobile: str) -> Optional[dict]:
    """Look up a user by mobile number."""
    with get_db() as db:
        user = db.query(User).filter(User.mobile == mobile, User.is_active == True).first()
        return _user_dict(user) if user else None


def authenticate_with_otp(mobile: str, otp_code: str) -> Tuple[Optional[dict], str]:
    """
    Verify OTP for mobile login.
    Returns (user_dict, "") on success, (None, error_message) on failure.
    """
    from .otp_service import verify_otp

    with get_db() as db:
        user = db.query(User).filter(User.mobile == mobile, User.is_active == True).first()
        if not user:
            return None, "Mobile number not registered."

        if _is_locked(user):
            remaining = int((user.lockout_until - datetime.utcnow()).total_seconds() / 60)
            return None, f"Account temporarily locked. Try again in {remaining} minute(s)."

        ok, msg = verify_otp(otp_code, mobile=mobile, purpose="login")
        if not ok:
            _record_failed_login(db, user)
            _audit(db, user.id, "otp_fail", "user", user.id, f"OTP fail: {mobile}")
            return None, msg

        # Success
        _reset_failed_login(db, user)
        user.last_login = datetime.utcnow()
        _audit(db, user.id, "login_otp", "user", user.id, f"OTP login: {mobile}")
        return _user_dict(user), ""


# ── Password-Based Authentication (admin / fallback) ─────────────────────────

def authenticate(email: str, password: str) -> Tuple[Optional[dict], str]:
    """
    Authenticate by email + password.
    Returns (user_dict, "") on success, (None, error_message) on failure.
    """
    with get_db() as db:
        user = db.query(User).filter(User.email == email, User.is_active == True).first()
        if not user:
            return None, "Invalid credentials."

        if _is_locked(user):
            remaining = int((user.lockout_until - datetime.utcnow()).total_seconds() / 60)
            return None, f"Account temporarily locked. Try again in {remaining} minute(s)."

        if not verify_password(password, user.password_hash):
            _record_failed_login(db, user)
            _audit(db, user.id, "login_fail", "user", user.id, f"Bad password: {email}")
            left = MAX_FAILED_ATTEMPTS - (user.failed_login_attempts or 0)
            if left <= 2:
                return None, f"Incorrect password. {left} attempt(s) before lockout."
            return None, "Invalid credentials."

        _reset_failed_login(db, user)
        user.last_login = datetime.utcnow()
        _audit(db, user.id, "login_pw", "user", user.id, f"Password login: {email}")
        return _user_dict(user), ""


# ── User CRUD ─────────────────────────────────────────────────────────────────

def get_user_by_id(user_id: int) -> Optional[dict]:
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        return _user_dict(user) if user else None


def get_user_by_email(email: str) -> Optional[dict]:
    with get_db() as db:
        user = db.query(User).filter(User.email == email).first()
        return _user_dict(user) if user else None


def get_all_users() -> list:
    with get_db() as db:
        return [_user_dict(u) for u in db.query(User).order_by(User.created_at.desc()).all()]


def admin_create_user(
    email: str,
    mobile: str,
    full_name: str,
    role: str,
    department: str = "",
    created_by_id: Optional[int] = None,
    smtp_cfg: Optional[dict] = None,
) -> Tuple[bool, str]:
    """
    Admin-only user creation.
    Generates a temp password, forces password change on first login,
    and emails credentials.
    """
    with get_db() as db:
        if db.query(User).filter(User.email == email).first():
            return False, "Email already registered."
        if mobile and db.query(User).filter(User.mobile == mobile).first():
            return False, "Mobile number already registered."

    temp_password = _generate_temp_password()

    with get_db() as db:
        user = User(
            email=email,
            mobile=mobile,
            password_hash=hash_password(temp_password),
            full_name=full_name,
            role=role,
            department=department,
            plan="free",
            is_active=True,
            force_password_change=True,
            created_by_id=created_by_id,
        )
        db.add(user)
        db.flush()
        _audit(db, created_by_id, "user_create", "user", user.id,
               f"Admin created: {email} ({role})")

    # Send welcome email
    if smtp_cfg and smtp_cfg.get("smtp_host"):
        _send_welcome_email(email, full_name, temp_password, role, smtp_cfg)

    return True, temp_password


def update_user(user_id: int, updates: dict, updated_by_id: Optional[int] = None) -> Tuple[bool, str]:
    """Update user fields. Allowed: full_name, mobile, role, department, is_active, plan."""
    allowed = {"full_name", "mobile", "role", "department", "is_active", "plan"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found."
        for k, v in updates.items():
            setattr(user, k, v)
        _audit(db, updated_by_id, "user_update", "user", user_id,
               f"Updated: {list(updates.keys())}")
    return True, "User updated."


def change_password(user_id: int, new_password: str, force: bool = False) -> Tuple[bool, str]:
    if len(new_password) < 8:
        return False, "Password must be at least 8 characters."
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found."
        user.password_hash         = hash_password(new_password)
        user.force_password_change = False
        revoke_all_refresh_tokens(user_id)
        _audit(db, user_id, "password_change", "user", user_id, "Password changed")
    return True, "Password updated."


def deactivate_user(user_id: int, by_id: Optional[int] = None) -> Tuple[bool, str]:
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found."
        user.is_active = False
        revoke_all_refresh_tokens(user_id)
        _audit(db, by_id, "user_deactivate", "user", user_id, f"Deactivated: {user.email}")
    return True, "User deactivated."


def reactivate_user(user_id: int, by_id: Optional[int] = None) -> Tuple[bool, str]:
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found."
        user.is_active             = True
        user.failed_login_attempts = 0
        user.lockout_until         = None
        _audit(db, by_id, "user_reactivate", "user", user_id, f"Reactivated: {user.email}")
    return True, "User reactivated."


# ── TOTP Management ───────────────────────────────────────────────────────────

def setup_totp(user_id: int) -> Tuple[str, str]:
    """
    Generate a new TOTP secret for a user.
    Returns (secret, qr_base64). Call confirm_totp() to activate.
    """
    from .otp_service import generate_totp_secret, generate_totp_qr_base64
    secret = generate_totp_secret()
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.totp_secret  = secret
            user.totp_enabled = False   # not enabled until confirmed
            email = user.email
    qr = generate_totp_qr_base64(secret, email) or ""
    return secret, qr


def confirm_totp(user_id: int, code: str) -> Tuple[bool, str]:
    """Verify the code and enable TOTP for the user."""
    from .otp_service import verify_totp
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.totp_secret:
            return False, "TOTP not set up."
        if verify_totp(user.totp_secret, code):
            user.totp_enabled = True
            _audit(db, user_id, "totp_enabled", "user", user_id, "TOTP activated")
            return True, "Authenticator app linked successfully."
        return False, "Invalid code. Please try again."


def disable_totp(user_id: int) -> Tuple[bool, str]:
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.totp_secret  = None
            user.totp_enabled = False
            _audit(db, user_id, "totp_disabled", "user", user_id, "TOTP disabled")
    return True, "TOTP disabled."


# ── Plan helpers ──────────────────────────────────────────────────────────────

def update_user_plan(user_id: int, plan: str):
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.plan = plan
            _audit(db, user_id, "plan_change", "user", user_id, f"Plan → {plan}")


def get_plan_limits(plan: str) -> dict:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


# ── Audit Log ─────────────────────────────────────────────────────────────────

def log_audit(user_id: Optional[int], action: str, resource: str,
              resource_id: Optional[int] = None, details: str = ""):
    with get_db() as db:
        _audit(db, user_id, action, resource, resource_id, details)


def get_audit_logs(limit: int = 50) -> list:
    with get_db() as db:
        logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
        return [{
            "id":          l.id,
            "user_id":     l.user_id,
            "action":      l.action,
            "resource":    l.resource,
            "resource_id": l.resource_id,
            "details":     l.details,
            "created_at":  l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else "",
        } for l in logs]


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _audit(db, user_id, action, resource, resource_id, details):
    db.add(AuditLog(user_id=user_id, action=action, resource=resource,
                    resource_id=resource_id, details=str(details)[:500]))


def _user_dict(u: User) -> dict:
    return {
        "id":                    u.id,
        "email":                 u.email,
        "mobile":                u.mobile or "",
        "full_name":             u.full_name or "",
        "role":                  u.role,
        "department":            u.department or "",
        "plan":                  u.plan,
        "is_active":             u.is_active,
        "force_password_change": u.force_password_change or False,
        "totp_enabled":          u.totp_enabled or False,
        "last_login":            u.last_login.strftime("%Y-%m-%d %H:%M") if u.last_login else "",
        "created_at":            u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
        "created_by_id":         u.created_by_id,
    }


def _generate_temp_password(length: int = 12) -> str:
    import string as _str
    chars = _str.ascii_letters + _str.digits + "@#$!"
    pwd   = [
        secrets.choice(_str.ascii_uppercase),
        secrets.choice(_str.ascii_lowercase),
        secrets.choice(_str.digits),
        secrets.choice("@#$!"),
    ]
    pwd += [secrets.choice(chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


def _send_welcome_email(email: str, full_name: str, temp_password: str,
                        role: str, smtp_cfg: dict):
    """Send welcome email with credentials to a newly created user."""
    try:
        msg             = MIMEMultipart("alternative")
        msg["Subject"]  = "Welcome to BraveAspire — Your Account Details"
        msg["From"]     = smtp_cfg.get("from_email", "noreply@braveaspire.com")
        msg["To"]       = email

        html = f"""
        <div style="font-family:sans-serif;max-width:520px;margin:auto;
          background:#12102A;color:#E2E0F0;padding:2rem;border-radius:12px">
          <h2 style="color:#7C3AED">Welcome to BraveAspire 🚀</h2>
          <p>Hi {full_name},</p>
          <p>Your account has been created by the admin. Here are your login credentials:</p>
          <div style="background:#1A1830;border:1px solid #2D2556;border-radius:8px;
            padding:1rem;margin:1rem 0">
            <p><strong>Email:</strong> {email}</p>
            <p><strong>Temporary Password:</strong>
              <code style="color:#C4B5FD;font-size:1.1rem">{temp_password}</code></p>
            <p><strong>Role:</strong> {role.replace('_',' ').title()}</p>
          </div>
          <p style="color:#F87171"><strong>⚠️ You will be required to change your password on first login.</strong></p>
          <p style="color:#9B8FD4;font-size:.85rem">
            Login at your company's BraveAspire portal. Do not share these credentials.
          </p>
        </div>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(smtp_cfg["smtp_host"], int(smtp_cfg.get("smtp_port", 587)), timeout=15) as s:
            s.ehlo(); s.starttls()
            if smtp_cfg.get("smtp_user"):
                s.login(smtp_cfg["smtp_user"], smtp_cfg.get("smtp_password", ""))
            s.sendmail(msg["From"], [email], msg.as_string())
        log.info("Welcome email sent to %s", email)
    except Exception as e:
        log.error("Welcome email failed: %s", e)


# ── Legacy compatibility ──────────────────────────────────────────────────────

def register_user(email: str, password: str, full_name: str = "", role: str = "sales_executive") -> Tuple[bool, str]:
    """Legacy function — used only internally. Public signup is disabled."""
    with get_db() as db:
        if db.query(User).filter(User.email == email).first():
            return False, "Email already registered."
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
            plan="free",
        )
        db.add(user)
        db.flush()
        _audit(db, user.id, "register", "user", user.id, f"Registered: {email}")
        return True, "Registration successful."
