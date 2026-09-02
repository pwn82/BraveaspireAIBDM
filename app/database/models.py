import uuid
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float,
    Boolean, ForeignKey, Enum, BigInteger, Index,
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


def _uuid():
    return str(uuid.uuid4())


# ── Roles ─────────────────────────────────────────────────────────────────────
ROLES = ["super_admin", "admin", "sales_manager", "bdm", "sales_executive", "viewer"]


# ── Multi-tenancy ─────────────────────────────────────────────────────────────
# Phase 1 (Chunk 1): additive-only. `organization_id` columns on tenant tables
# are nullable at this stage so existing rows keep working. A backfill in
# db.py assigns every legacy row to a "Default Organization" on first boot.
# Chunk 2 will make these columns required and rewrite every query.

class Organization(Base):
    __tablename__ = "organizations"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(200), nullable=False)
    slug       = Column(String(100), unique=True, nullable=False, index=True)
    status     = Column(String(30),  default="active")     # active | suspended | deleted
    # Phase 7: O(1) plan lookup. Kept in sync with the active Subscription row
    # by the Stripe webhook. Default plan is "free" so a brand-new org gets
    # the free-tier limits without needing a Subscription row.
    plan       = Column(String(20),  default="free")       # free | starter | pro | agency
    created_at = Column(DateTime,    default=datetime.utcnow)
    updated_at = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    members = relationship("OrganizationUser", back_populates="organization", cascade="all, delete-orphan")


class OrganizationUser(Base):
    """User membership in an organization (many-to-many with a role)."""
    __tablename__ = "organization_users"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"),         nullable=False, index=True)
    role            = Column(String(30), default="sales_executive")   # role within this org
    status          = Column(String(20), default="active")            # active | invited | removed
    created_at      = Column(DateTime,   default=datetime.utcnow)

    organization = relationship("Organization", back_populates="members")
    user         = relationship("User",         back_populates="org_memberships")


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

    subscription    = relationship("Subscription",     back_populates="user", uselist=False)
    audit_logs      = relationship("AuditLog",         back_populates="user")
    refresh_tokens  = relationship("RefreshToken",     back_populates="user", cascade="all, delete-orphan")
    otp_codes       = relationship("OTPCode",          back_populates="user", cascade="all, delete-orphan")
    org_memberships = relationship("OrganizationUser", back_populates="user", cascade="all, delete-orphan")


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
    # Phase 7: subscriptions belong to organizations, not users. `user_id` is
    # kept for backwards-compat with the pre-Phase-1 single-user code; the
    # authoritative link is `organization_id`.
    organization_id        = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id                = Column(Integer, ForeignKey("users.id"))
    plan                   = Column(String(20), default="free")
    stripe_customer_id     = Column(String(100), index=True)
    stripe_subscription_id = Column(String(100), unique=True, index=True)
    stripe_session_id      = Column(String(200))
    status                 = Column(String(30), default="inactive")
    current_period_start   = Column(DateTime)
    current_period_end     = Column(DateTime)
    created_at             = Column(DateTime, default=datetime.utcnow)
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscription")


class StripeEvent(Base):
    """
    Phase 7: Stripe webhook idempotency ledger.

    Stripe retries webhooks aggressively (up to 3 days). Without this table,
    a retried `invoice.paid` event double-processes and could double-provision.
    Row insert on first receipt is unique-constrained on event_id; subsequent
    receipts hit the constraint and short-circuit.
    """
    __tablename__ = "stripe_events"

    id           = Column(Integer, primary_key=True, index=True)
    event_id     = Column(String(100), unique=True, nullable=False, index=True)
    event_type   = Column(String(80),  nullable=False)
    status       = Column(String(20),  default="processed")   # processed | error
    error        = Column(Text,        nullable=True)
    raw_payload  = Column(Text,        nullable=True)
    processed_at = Column(DateTime,    default=datetime.utcnow)
    created_at   = Column(DateTime,    default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True)
    action          = Column(String(100))
    resource    = Column(String(50))
    resource_id = Column(Integer, nullable=True)
    details     = Column(Text)
    ip_address  = Column(String(50))
    created_at  = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")


# ── CRM ───────────────────────────────────────────────────────────────────────

class Company(Base):
    __tablename__ = "companies"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    name            = Column(String(300), nullable=False)
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

    __table_args__ = (
        Index("ix_companies_org_status",  "organization_id", "status"),
        Index("ix_companies_org_created", "organization_id", "created_at"),
    )


class Contact(Base):
    __tablename__ = "contacts"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    company_id      = Column(Integer, ForeignKey("companies.id"))
    name            = Column(String(100), nullable=False)
    designation = Column(String(100))
    email       = Column(String(200))
    linkedin    = Column(String(500))
    phone       = Column(String(50))
    verified    = Column(Boolean, default=False)
    notes       = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)
    # Contact email verification lifecycle (P0 hardening — see OutreachPolicy).
    # unknown | inferred | unverified | verified | bounced | suppressed
    # "inferred" = AI guessed this address (e.g. firstname@domain pattern) and
    # it must never be used for outreach until a human promotes it.
    email_status       = Column(String(20), default="unknown", nullable=False)
    email_source       = Column(String(30), nullable=True)   # manual | ai_guess | scrape | import | verified_api
    email_confidence   = Column(Float,      nullable=True)
    email_verified_at  = Column(DateTime,   nullable=True)

    company  = relationship("Company", back_populates="contacts")
    outreach = relationship("Outreach", back_populates="contact", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_contacts_org_email", "organization_id", "email"),
    )


class Outreach(Base):
    __tablename__ = "outreach"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    contact_id      = Column(Integer, ForeignKey("contacts.id"))
    subject         = Column(Text)
    body            = Column(Text)
    status          = Column(String(50), default="Draft")
    channel         = Column(String(30), default="Email")
    # Tracking
    tracking_id     = Column(String(36), default=_uuid, unique=True, index=True)
    open_count      = Column(Integer, default=0)
    click_count     = Column(Integer, default=0)
    # Phase 5: reply threading + provider correlation
    message_id_header    = Column(String(255), nullable=True, index=True)  # our outbound Message-ID
    in_reply_to          = Column(String(255), nullable=True)              # what we're replying to (thread)
    provider_message_id  = Column(String(255), nullable=True, index=True)  # id returned by SES/Mailgun/etc.
    bounce_status        = Column(String(20),  nullable=True)              # delivered | soft | hard | complaint
    unsubscribed_at      = Column(DateTime,    nullable=True)              # this recipient clicked unsub
    # Timestamps
    sent_at         = Column(DateTime)
    opened_at       = Column(DateTime)
    replied_at      = Column(DateTime)
    follow_up_count = Column(Integer, default=0)
    next_followup_at= Column(DateTime)
    created_at      = Column(DateTime, default=datetime.utcnow)
    # Human-in-the-loop approval trail (OutreachPolicy requires this before send).
    approved_by     = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at     = Column(DateTime, nullable=True)

    contact  = relationship("Contact", back_populates="outreach")
    followups= relationship("FollowUp", back_populates="outreach", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_outreach_org_status",    "organization_id", "status"),
        Index("ix_outreach_next_followup", "next_followup_at"),
    )


class FollowUp(Base):
    __tablename__ = "followups"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    outreach_id     = Column(Integer, ForeignKey("outreach.id"))
    subject         = Column(Text)
    body            = Column(Text)
    sequence_number = Column(Integer, default=1)
    scheduled_at    = Column(DateTime)
    sent_at         = Column(DateTime)
    status          = Column(String(50), default="Scheduled")
    created_at      = Column(DateTime, default=datetime.utcnow)

    outreach = relationship("Outreach", back_populates="followups")

    __table_args__ = (
        Index("ix_followups_org_status_sch", "organization_id", "status", "scheduled_at"),
    )


class SuppressionList(Base):
    """
    Phase 5: emails that must never be sent by this org.

    Reasons: unsubscribe | bounce | complaint | manual_block | do_not_contact
    Email is stored lowercased; the EmailService normalizes on write and read.
    Uniqueness (org_id, email) is enforced at the DB level.
    """
    __tablename__ = "suppression_list"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    email           = Column(String(320), nullable=False, index=True)  # 320 = RFC5321 max
    reason          = Column(String(30),  nullable=False)
    source          = Column(String(50),  nullable=True)   # unsub_click, bounce_webhook, admin_ui, imap_reply
    notes           = Column(Text,        nullable=True)
    created_at      = Column(DateTime,    default=datetime.utcnow)

    __table_args__ = (
        Index("uq_suppression_org_email", "organization_id", "email", unique=True),
    )


class BounceEvent(Base):
    """
    Phase 5: append-only log of bounce / complaint webhooks.

    A hard bounce or complaint here is what drives an auto-insert into
    SuppressionList. Soft bounces are recorded but do NOT auto-suppress —
    they inform per-recipient throttling decisions later.
    """
    __tablename__ = "bounce_events"

    id                   = Column(Integer, primary_key=True, index=True)
    organization_id      = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    outreach_id          = Column(Integer, ForeignKey("outreach.id"),      nullable=True, index=True)
    email                = Column(String(320), nullable=False, index=True)
    bounce_type          = Column(String(20),  nullable=False)   # hard | soft | complaint | delivered
    provider             = Column(String(50),  nullable=True)    # ses | mailgun | sendgrid | imap | manual
    provider_message_id  = Column(String(255), nullable=True, index=True)
    diagnostic           = Column(Text, nullable=True)           # raw diagnostic text
    raw_payload          = Column(Text, nullable=True)           # full provider JSON, for auditing
    created_at           = Column(DateTime, default=datetime.utcnow)


class WorkflowRun(Base):
    """
    Phase 4: durable record of a background job / workflow execution.

    idempotency_key = a caller-supplied token that dedupes retries. Uniqueness
    is enforced per organization so two orgs can independently use the same key.
    A finished run (succeeded / dead) short-circuits any re-submission with the
    same key — critical for "don't send the email twice" and "webhook retries
    don't double-charge".
    """
    __tablename__ = "workflow_runs"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    workflow_name   = Column(String(100), nullable=False, index=True)
    idempotency_key = Column(String(200), nullable=False, index=True)
    status          = Column(String(20),  nullable=False, default="queued")
    # queued | running | succeeded | failed | dead   (dead = permanent failure, DLQ)
    retry_count     = Column(Integer, default=0)
    max_retries     = Column(Integer, default=3)
    last_error      = Column(Text,    nullable=True)
    result          = Column(Text,    nullable=True)       # JSON blob if the job returns anything
    scheduled_at    = Column(DateTime, default=datetime.utcnow)
    started_at      = Column(DateTime, nullable=True)
    finished_at     = Column(DateTime, nullable=True)
    next_retry_at   = Column(DateTime, nullable=True, index=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_workflow_runs_org_wf_idempotency",
              "organization_id", "workflow_name", "idempotency_key", unique=True),
        Index("ix_workflow_runs_status_next_retry", "status", "next_retry_at"),
    )


class AILog(Base):
    """
    Phase 6: cost + reliability ledger for every AI call.

    One row per invocation of AIGateway. `status` distinguishes real
    failures from succeeded calls (Phase 6 stops using error-as-content).
    Cost is stored in micro-USD to avoid float arithmetic on money.
    """
    __tablename__ = "ai_logs"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    agent_name      = Column(String(100))
    task            = Column(Text)
    result          = Column(Text)
    provider        = Column(String(50))
    model           = Column(String(100))
    duration_ms     = Column(Integer)
    created_at      = Column(DateTime, default=datetime.utcnow)
    # Phase 6 additions:
    status          = Column(String(20),  nullable=True, index=True)  # ok | error | timeout | schema_invalid | quota_exhausted
    error           = Column(Text,        nullable=True)              # sanitized error string when status != ok
    input_tokens    = Column(Integer,     nullable=True)
    output_tokens   = Column(Integer,     nullable=True)
    cost_micro_usd  = Column(Integer,     nullable=True)              # 1_000_000 = $1.00
    contains_untrusted = Column(Boolean,  default=False)              # true if request wrapped external text

    __table_args__ = (
        Index("ix_ai_logs_org_created", "organization_id", "created_at"),
    )
