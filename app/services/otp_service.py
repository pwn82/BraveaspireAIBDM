"""
OTP Service
===========
Handles:
  • 6-digit numeric OTP generation and storage (SMS via Twilio or email fallback)
  • TOTP (authenticator app) setup and verification via pyotp
  • Rate limiting: max 3 OTPs per mobile/email per 10-minute window
"""

import os
import random
import string
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from ..database.db import get_db
from ..database.models import OTPCode, User

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
OTP_LENGTH          = 6
OTP_EXPIRY_MINUTES  = 10
OTP_MAX_ATTEMPTS    = 3         # max wrong guesses before code is invalidated
OTP_RATE_LIMIT      = 3         # max new OTPs per mobile/email per window
OTP_RATE_WINDOW_MIN = 10        # minutes for rate-limit window

TWILIO_SID    = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN",  "")
TWILIO_FROM   = os.getenv("TWILIO_FROM_NUMBER", "")


# ── OTP Generation ────────────────────────────────────────────────────────────

def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=OTP_LENGTH))


def _rate_check(mobile: Optional[str], email: Optional[str]) -> bool:
    """Return True if within rate limit (may send). False if too many recent OTPs."""
    window_start = datetime.utcnow() - timedelta(minutes=OTP_RATE_WINDOW_MIN)
    with get_db() as db:
        q = db.query(OTPCode).filter(OTPCode.created_at >= window_start)
        if mobile:
            q = q.filter(OTPCode.mobile == mobile)
        elif email:
            q = q.filter(OTPCode.email == email)
        count = q.count()
    return count < OTP_RATE_LIMIT


def create_otp(
    mobile: Optional[str] = None,
    email: Optional[str] = None,
    purpose: str = "login",
    user_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """
    Generate and save a new OTP.
    Returns (True, code) on success or (False, error_message).
    """
    if not mobile and not email:
        return False, "Mobile or email is required to send OTP."

    if not _rate_check(mobile, email):
        return False, f"Too many OTP requests. Please wait {OTP_RATE_WINDOW_MIN} minutes."

    code = _generate_code()
    expires = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    with get_db() as db:
        # Invalidate any previous unused OTPs for same target+purpose
        prev = db.query(OTPCode).filter(
            OTPCode.used == False,
            OTPCode.expires_at > datetime.utcnow(),
        )
        if mobile:
            prev = prev.filter(OTPCode.mobile == mobile, OTPCode.purpose == purpose)
        elif email:
            prev = prev.filter(OTPCode.email == email, OTPCode.purpose == purpose)
        for old in prev.all():
            old.used = True   # invalidate

        otp_row = OTPCode(
            user_id=user_id,
            mobile=mobile,
            email=email,
            code=code,
            purpose=purpose,
            expires_at=expires,
        )
        db.add(otp_row)

    return True, code


def verify_otp(
    code: str,
    mobile: Optional[str] = None,
    email: Optional[str] = None,
    purpose: str = "login",
) -> Tuple[bool, str]:
    """
    Verify an OTP code.
    Returns (True, "ok") or (False, error_message).
    Increments attempt counter; marks as used on success.
    """
    with get_db() as db:
        q = db.query(OTPCode).filter(
            OTPCode.used == False,
            OTPCode.expires_at > datetime.utcnow(),
            OTPCode.purpose == purpose,
        )
        if mobile:
            q = q.filter(OTPCode.mobile == mobile)
        elif email:
            q = q.filter(OTPCode.email == email)

        otp_row = q.order_by(OTPCode.created_at.desc()).first()

        if not otp_row:
            return False, "OTP not found or has expired. Please request a new one."

        otp_row.attempts += 1

        if otp_row.attempts > OTP_MAX_ATTEMPTS:
            otp_row.used = True
            return False, "Too many incorrect attempts. Please request a new OTP."

        if otp_row.code != code.strip():
            remaining = OTP_MAX_ATTEMPTS - otp_row.attempts
            if remaining <= 0:
                otp_row.used = True
                return False, "Too many incorrect attempts. Please request a new OTP."
            return False, f"Incorrect OTP. {remaining} attempt(s) remaining."

        # ✅ Correct
        otp_row.used = True
        return True, "ok"


# ── SMS Delivery ──────────────────────────────────────────────────────────────

def send_sms_otp(mobile: str, code: str) -> Tuple[bool, str]:
    """Send OTP via Twilio SMS. Falls back gracefully if not configured."""
    if not TWILIO_SID or not TWILIO_TOKEN or not TWILIO_FROM:
        log.warning("Twilio not configured — OTP would be: %s (for %s)", code, mobile)
        # In dev mode without Twilio, return success so login can proceed
        return True, "OTP generated (Twilio not configured — check logs for dev code)"

    try:
        from twilio.rest import Client as TwilioClient
        client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
        message = client.messages.create(
            body=f"Your BraveAspire login OTP is: {code}. Valid for {OTP_EXPIRY_MINUTES} minutes. Do not share.",
            from_=TWILIO_FROM,
            to=mobile,
        )
        log.info("SMS OTP sent to %s, SID=%s", mobile, message.sid)
        return True, "OTP sent successfully."
    except Exception as e:
        log.error("Twilio SMS failed: %s", e)
        return False, f"Failed to send SMS: {str(e)}"


def send_email_otp(to_email: str, code: str, smtp_cfg: dict) -> Tuple[bool, str]:
    """Send OTP via email (fallback when SMS is unavailable)."""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "BraveAspire — Your Login OTP"
        msg["From"]    = smtp_cfg.get("from_email", "noreply@braveaspire.com")
        msg["To"]      = to_email

        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;
          background:#12102A;color:#E2E0F0;padding:2rem;border-radius:12px">
          <h2 style="color:#7C3AED">BraveAspire</h2>
          <p>Your one-time login code is:</p>
          <div style="font-size:2rem;font-weight:800;letter-spacing:.3em;
            color:#C4B5FD;text-align:center;padding:1rem;
            background:#1A1830;border-radius:8px;margin:1rem 0">
            {code}
          </div>
          <p style="color:#9B8FD4;font-size:.85rem">
            Valid for {OTP_EXPIRY_MINUTES} minutes. Do not share this code.
          </p>
        </div>
        """
        msg.attach(MIMEText(html, "html"))

        host  = smtp_cfg.get("smtp_host", "")
        port  = int(smtp_cfg.get("smtp_port", 587))
        user  = smtp_cfg.get("smtp_user", "")
        pw    = smtp_cfg.get("smtp_password", "")

        if not host:
            return False, "SMTP not configured."

        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            if user and pw:
                server.login(user, pw)
            server.sendmail(msg["From"], [to_email], msg.as_string())

        return True, "OTP sent to email."
    except Exception as e:
        log.error("Email OTP failed: %s", e)
        return False, f"Failed to send email OTP: {str(e)}"


# ── TOTP (Authenticator App) ──────────────────────────────────────────────────

def generate_totp_secret() -> str:
    """Generate a new TOTP secret."""
    try:
        import pyotp
        return pyotp.random_base32()
    except ImportError:
        import base64, os
        return base64.b32encode(os.urandom(20)).decode("utf-8")


def get_totp_provisioning_uri(secret: str, email: str, issuer: str = "BraveAspire") -> str:
    """Return the otpauth:// URI for QR code generation."""
    try:
        import pyotp
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=issuer)
    except ImportError:
        return f"otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}"


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code. Accepts ±1 window (30-second tolerance)."""
    try:
        import pyotp
        totp = pyotp.TOTP(secret)
        return totp.verify(code.strip(), valid_window=1)
    except ImportError:
        return False
    except Exception:
        return False


def generate_totp_qr_base64(secret: str, email: str) -> Optional[str]:
    """Return a base64-encoded PNG QR code for the TOTP URI."""
    try:
        import qrcode
        import io
        import base64

        uri = get_totp_provisioning_uri(secret, email)

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        # Use standard black-on-white for maximum scanner compatibility
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    except ImportError:
        log.warning("qrcode/Pillow not installed. Run: pip install 'qrcode[pil]' Pillow")
        return None
    except Exception as e:
        log.warning("QR generation failed: %s", e)
        return None
