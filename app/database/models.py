import uuid
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float,
    Boolean, ForeignKey, Enum, BigInteger
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


def _uuid():
    return str(uuid.uuid4())


# ── Roles ─────────────────────────────────────────────────────────────────────
ROLES = ["super_admin", "admin", "sales_manager", "bdm", "sales_executive", "viewer"]


# ── Users & Auth ──────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id                    = Column(Integer, primary_key=True, index=True)
    email                 = Column(String(200), unique=True, nullable=False, index=True)
    mobile                = Column(String(20),  unique=True, nullable=True,  index=True)
    password_hash         = Column(String(256), nullable=False)
    full_name             = Column(String(150))
    department            = Column(String(100))
    role                  = Column(String(30), default="sales_executive")   # see ROLES
    plan                  = Column(String(20), default="free")              # free | starter | pro | agency
    is_active             = Column(Boolean, default=True)
    force_password_change = Column(Boolean, default=False)  # set True on admin-created accounts
    # Security / lockout
    failed_login_attempts = Column(Integer, default=0)
    lockout_until         = Column(DateTime, nullable=True)
    # TOTP
    totp_secret           = Column(String(64),  nullable=True)
    totp_enabled          = Column(Boolean, default=False)
    # Metadata
    created_by_id         = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at            = Column(DateTime, default=datetime.utcnow)
    last_login            = Column(DateTime)

    subscription  = relationship("Subscription",  back_populates="user",  uselist=False)
    audit_logs    = relationship("AuditLog",       back_populates="user")
    refresh_tokens= relationship("RefreshToken",   back_populates="user",  cascade="all, delete-orphan")
    otp_codes     = relationship("OTPCode",        back_populates="user",  cascade="all, delete-orphan")


class OTPCode(Base):
    """Short-lived OTP codes for mobile-based login and email verification."""
    __tablename__ = "otp_codes"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable for pre-auth lookup
    mobile     = Column(String(20), nullable=True, index=True)
    email      = Column(String(200), nullable=True, index=True)
    code       = Column(String(10),  nullable=False)
    purpose    = Column(String(30),  default="login")  # login | email_verify | password_reset
    expires_at = Column(DateTime,    nullable=False)
    used       = Column(Boolean,     default=False)
    attempts   = Column(Integer,     default=0)
    created_at = Column(DateTime,    default=datetime.utcnow)

    user = relationship("User", back_populates="otp_codes")


class RefreshToken(Base):
    """Long-lived refresh tokens for silent re-auth."""
    __tablename__ = "refresh_tokens"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash  = Column(String(256), unique=True, nullable=False, index=True)
    device_hint = Column(String(200))  # user-agent snippet for display
    expires_at  = Column(DateTime,    nullable=False)
    revoked     = Column(Boolean,     default=False)
    created_at  = Column(DateTime,    default=datetime.utcnow)
    last_used   = Column(DateTime,    nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id                     = Column(Integer, primary_key=True)
    user_id                = Column(Integer, ForeignKey("users.id"))
    plan                   = Column(String(20), default="free")
    stripe_customer_id     = Column(String(100))
    stripe_subscription_id = Column(String(100))
    stripe_session_id      = Column(String(200))
    status                 = Column(String(30), default="inactive")
    current_period_start   = Column(DateTime)
    current_period_end     = Column(DateTime)
    created_at             = Column(DateTime, default=datetime.utcnow)
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscription")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True)
    action      = Column(String(100))
    resource    = Column(String(50))
    resource_id = Column(Integer, nullable=True)
    details     = Column(Text)
    ip_address  = Column(String(50))
    created_at  = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")


# ── CRM ───────────────────────────────────────────────────────────────────────

class Company(Base):
    __tablename__ = "companies"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(300), nullable=False)
    website       = Column(String(500))
    industry      = Column(String(200))
    location      = Column(String(500))     # Google Maps addresses can be ~200+ chars
    employee_size = Column(Integer, default=0)
    revenue       = Column(String(100))
    score         = Column(Integer, default=0)
    status        = Column(String(50), default="New")
    hiring_status = Column(Boolean, default=False)
    tech_stack    = Column(Text)
    pain_points   = Column(Text)
    notes         = Column(Text)
    source        = Column(String(150), default="Manual")
    # Extended scraping fields
    linkedin_url      = Column(String(500))
    funding_stage     = Column(String(50))
    funding_amount    = Column(String(50))
    founded_year      = Column(Integer)
    job_openings      = Column(Integer, default=0)
    crunchbase_url    = Column(String(500))
    apollo_id         = Column(String(100))
    # Metadata
    created_by    = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacts = relationship("Contact", back_populates="company", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id          = Column(Integer, primary_key=True, index=True)
    company_id  = Column(Integer, ForeignKey("companies.id"))
    name        = Column(String(100), nullable=False)
    designation = Column(String(100))
    email       = Column(String(200))
    linkedin    = Column(String(500))
    phone       = Column(String(50))
    verified    = Column(Boolean, default=False)
    notes       = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)

    company  = relationship("Company", back_populates="contacts")
    outreach = relationship("Outreach", back_populates="contact", cascade="all, delete-orphan")


class Outreach(Base):
    __tablename__ = "outreach"

    id              = Column(Integer, primary_key=True, index=True)
    contact_id      = Column(Integer, ForeignKey("contacts.id"))
    subject         = Column(Text)
    body            = Column(Text)
    status          = Column(String(50), default="Draft")
    channel         = Column(String(30), default="Email")
    # Tracking
    tracking_id     = Column(String(36), default=_uuid, unique=True, index=True)
    open_count      = Column(Integer, default=0)
    click_count     = Column(Integer, default=0)
    # Timestamps
    sent_at         = Column(DateTime)
    opened_at       = Column(DateTime)
    replied_at      = Column(DateTime)
    follow_up_count = Column(Integer, default=0)
    next_followup_at= Column(DateTime)
    created_at      = Column(DateTime, default=datetime.utcnow)

    contact  = relationship("Contact", back_populates="outreach")
    followups= relationship("FollowUp", back_populates="outreach", cascade="all, delete-orphan")


class FollowUp(Base):
    __tablename__ = "followups"

    id              = Column(Integer, primary_key=True, index=True)
    outreach_id     = Column(Integer, ForeignKey("outreach.id"))
    subject         = Column(Text)
    body            = Column(Text)
    sequence_number = Column(Integer, default=1)
    scheduled_at    = Column(DateTime)
    sent_at         = Column(DateTime)
    status          = Column(String(50), default="Scheduled")
    created_at      = Column(DateTime, default=datetime.utcnow)

    outreach = relationship("Outreach", back_populates="followups")


class AILog(Base):
    __tablename__ = "ai_logs"

    id          = Column(Integer, primary_key=True, index=True)
    agent_name  = Column(String(100))
    task        = Column(Text)
    result      = Column(Text)
    provider    = Column(String(50))
    model       = Column(String(100))
    duration_ms = Column(Integer)
    created_at  = Column(DateTime, default=datetime.utcnow)
