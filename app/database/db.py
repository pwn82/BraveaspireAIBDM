import os
import logging
import platform
from contextlib import contextmanager
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker
from .models import (
    Base, Company, Contact, Outreach, FollowUp, User,
    Organization, OrganizationUser, AILog, AuditLog,
)

log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH  = os.path.join(DATA_DIR, "bdm.db")

# ── Cloud / hosted environment detection ─────────────────────────────────────
# Streamlit Cloud, Heroku, Railway, Render etc. don't have local SQL Server.
# We detect these and force SQLite regardless of USE_SQLSERVER setting.
def _is_cloud_env() -> bool:
    # Streamlit Cloud mounts apps under /mount/src/
    if os.path.exists("/mount/src"):
        return True
    # Streamlit Cloud sets this env var
    if os.getenv("STREAMLIT_RUNTIME_ENV") == "cloud":
        return True
    # Heroku
    if os.getenv("DYNO"):
        return True
    # Railway / Render / Fly.io
    if any(os.getenv(v) for v in ("RAILWAY_ENVIRONMENT", "RENDER", "FLY_APP_NAME")):
        return True
    # Linux without ODBC driver → almost certainly a cloud host
    if platform.system() == "Linux" and not os.path.exists("/usr/lib/libodbc.so"):
        return True
    return False

_IS_CLOUD = _is_cloud_env()

# ── Database URL ──────────────────────────────────────────────────────────────
# Priority:
#   1. DATABASE_URL env var (full SQLAlchemy URL — works with any DB)
#   2. AZURE_SQL_* env vars → cloud SQL Server via pymssql (Linux-friendly)
#   3. USE_SQLSERVER=true + local pyodbc (Windows + Trusted_Connection)
#   4. SQLite (default — works everywhere, no dependencies)
_DB_SERVER = os.getenv("DB_SERVER", "LAPTOP-5LTAD0QS\\SQLEXPRESS")
_DB_NAME   = os.getenv("DB_NAME",   "BraveAspireBDM")
_DB_DRIVER = os.getenv("DB_DRIVER", "ODBC+Driver+17+for+SQL+Server")

# Cloud SQL Server (Azure SQL / AWS RDS for SQL Server / etc.) via pymssql
_AZURE_SERVER   = os.getenv("AZURE_SQL_SERVER",   "")  # e.g. yourname.database.windows.net
_AZURE_DB       = os.getenv("AZURE_SQL_DATABASE", "")  # e.g. BraveAspireBDM
_AZURE_USER     = os.getenv("AZURE_SQL_USER",     "")  # e.g. sqladmin@yourname
_AZURE_PASSWORD = os.getenv("AZURE_SQL_PASSWORD", "")
_AZURE_PORT     = os.getenv("AZURE_SQL_PORT",     "1433")


def _build_mssql_url_pyodbc() -> str:
    """SQL Server URL via pyodbc (local Windows + Trusted_Connection)."""
    from urllib.parse import quote_plus
    driver  = _DB_DRIVER.replace("+", " ")
    odbc_cs = (
        f"DRIVER={{{driver}}};"
        f"SERVER={_DB_SERVER};"
        f"DATABASE={_DB_NAME};"
        f"Trusted_Connection=yes;"
        f"TrustServerCertificate=yes;"
    )
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_cs)}"


def _build_mssql_url_pymssql() -> str:
    """SQL Server URL via pymssql (cloud / Linux / Streamlit Cloud)."""
    from urllib.parse import quote_plus
    user = quote_plus(_AZURE_USER)
    pwd  = quote_plus(_AZURE_PASSWORD)
    return (
        f"mssql+pymssql://{user}:{pwd}@{_AZURE_SERVER}:{_AZURE_PORT}/{_AZURE_DB}"
        "?charset=utf8&tds_version=7.4"
    )


def _can_use_pyodbc() -> bool:
    """Local Windows path — pyodbc importable + not on cloud host."""
    if _IS_CLOUD:
        return False
    try:
        import pyodbc  # noqa: F401
        return True
    except ImportError:
        return False


def _can_use_pymssql() -> bool:
    """Cloud path — pymssql importable AND Azure SQL credentials configured."""
    if not (_AZURE_SERVER and _AZURE_DB and _AZURE_USER and _AZURE_PASSWORD):
        return False
    try:
        import pymssql  # noqa: F401
        return True
    except ImportError:
        return False


# ── Choose connection ─────────────────────────────────────────────────────────
DATABASE_URL = ""
_use_mssql   = False

if os.getenv("DATABASE_URL"):
    # 1. Highest priority — user-supplied full SQLAlchemy URL
    DATABASE_URL = os.getenv("DATABASE_URL")
    _use_mssql   = "mssql" in DATABASE_URL or "pyodbc" in DATABASE_URL or "pymssql" in DATABASE_URL
    log.info("DB: using DATABASE_URL → %s", DATABASE_URL.split("@")[-1][:60])

elif _can_use_pymssql():
    # 2. Azure SQL / cloud SQL Server via pymssql (works on Streamlit Cloud)
    DATABASE_URL = _build_mssql_url_pymssql()
    _use_mssql   = True
    log.info("DB: Azure/Cloud SQL Server (pymssql) → %s/%s", _AZURE_SERVER, _AZURE_DB)

elif os.getenv("USE_SQLSERVER", "false").lower() == "true" and _can_use_pyodbc():
    # 3. Local Windows SQL Server via pyodbc + Trusted Connection
    DATABASE_URL = _build_mssql_url_pyodbc()
    _use_mssql   = True
    log.info("DB: Local SQL Server (pyodbc) → %s\\%s", _DB_SERVER, _DB_NAME)

else:
    # 4. SQLite fallback
    os.makedirs(DATA_DIR, exist_ok=True)
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    _use_mssql   = False
    if _IS_CLOUD:
        log.info("DB: cloud env detected, no Azure SQL configured → SQLite (ephemeral!)")
    else:
        log.info("DB: SQLite default → %s", DB_PATH)

# ── Engine configuration ──────────────────────────────────────────────────────
_is_sqlite  = DATABASE_URL.startswith("sqlite")
_is_mssql   = _use_mssql

if _is_sqlite:
    _connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=_connect_args)
elif _is_mssql:
    _engine_kwargs = dict(
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,    # detect dropped connections
        pool_timeout=30,
        pool_recycle=1800,     # recycle connections every 30 min
    )
    # fast_executemany is a pyodbc-only option; pymssql rejects it.
    if "pyodbc" in DATABASE_URL:
        _engine_kwargs["fast_executemany"] = True
    engine = create_engine(DATABASE_URL, **_engine_kwargs)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── DB Initialization ─────────────────────────────────────────────────────────

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "vector_db"), exist_ok=True)

    # Schema management:
    #   • Fresh DB      → run migrations from 0001 forward.
    #   • Legacy DB     → stamp head (adopt current schema) then future upgrades apply.
    #   • Alembic broken/missing → fall back to Base.metadata.create_all() so dev still works.
    _run_migrations()

    # SQLite-only column migrations for very old dev DBs that predate Alembic
    # and are still missing model columns. Idempotent (each ALTER swallows the
    # "column already exists" error). Kept as a belt-and-braces for dev only.
    if _is_sqlite:
        _sqlite_migrate()

    _seed_admin()
    _bootstrap_default_org()


def _run_migrations():
    """Bring the DB schema up to head via Alembic; fall back to create_all on failure."""
    try:
        from alembic.config import Config
        from alembic import command
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext

        alembic_cfg = Config(os.path.join(BASE_DIR, "alembic.ini"))
        # env.py already imports DATABASE_URL from this module, so no override needed.

        # Detect pre-Alembic databases: tables exist but alembic_version doesn't.
        with engine.connect() as conn:
            mc = MigrationContext.configure(conn)
            current_rev = mc.get_current_revision()

        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        if current_rev is None:
            # Either brand new, or a legacy DB with existing tables.
            from sqlalchemy import inspect
            insp = inspect(engine)
            existing_tables = set(insp.get_table_names())
            # Any of our tables already there? Then this is a legacy dev DB
            # and we STAMP head instead of trying to re-create tables.
            model_tables = set(Base.metadata.tables.keys())
            if existing_tables & model_tables:
                log.info("Alembic: existing schema detected → stamp head (%s)", head_rev)
                command.stamp(alembic_cfg, "head")
            else:
                log.info("Alembic: empty DB → upgrade head (%s)", head_rev)
                command.upgrade(alembic_cfg, "head")
        elif current_rev != head_rev:
            log.info("Alembic: upgrading %s → %s", current_rev, head_rev)
            command.upgrade(alembic_cfg, "head")
        else:
            log.debug("Alembic: schema at head (%s)", head_rev)
    except Exception as e:
        log.warning("Alembic run failed (%s) — falling back to Base.metadata.create_all()", e)
        try:
            Base.metadata.create_all(bind=engine)
        except Exception as e2:
            log.warning("create_all fallback also failed: %s", e2)


def _sqlite_migrate():
    """Add columns introduced after initial SQLite release."""
    migrations = [
        ("outreach",  "tracking_id",   "TEXT"),
        ("outreach",  "open_count",    "INTEGER DEFAULT 0"),
        ("outreach",  "click_count",   "INTEGER DEFAULT 0"),
        ("outreach",  "channel",       "TEXT DEFAULT 'Email'"),
        ("companies", "created_by",    "INTEGER"),
        ("companies", "linkedin_url",  "TEXT"),
        ("companies", "funding_stage", "TEXT"),
        ("companies", "funding_amount","TEXT"),
        ("companies", "founded_year",  "INTEGER"),
        ("companies", "crunchbase_url","TEXT"),
        ("companies", "apollo_id",     "TEXT"),
        ("companies", "job_openings",  "INTEGER DEFAULT 0"),
        ("users",     "mobile",        "TEXT"),
        ("users",     "totp_secret",   "TEXT"),
        ("users",     "totp_enabled",  "INTEGER DEFAULT 0"),
        ("users",     "force_password_change", "INTEGER DEFAULT 0"),
        ("users",     "failed_login_attempts", "INTEGER DEFAULT 0"),
        ("users",     "lockout_until", "TEXT"),
        ("users",     "created_by_id", "INTEGER"),
        ("users",     "department",    "TEXT"),
        # Phase 1 (multi-tenancy) — nullable organization_id on every tenant table
        ("companies", "organization_id", "INTEGER"),
        ("contacts",  "organization_id", "INTEGER"),
        ("outreach",  "organization_id", "INTEGER"),
        ("followups", "organization_id", "INTEGER"),
        ("ai_logs",   "organization_id", "INTEGER"),
        ("ai_logs",   "user_id",         "INTEGER"),
        ("audit_logs","organization_id", "INTEGER"),
    ]
    with engine.connect() as conn:
        for table, col, col_type in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass  # column already exists


def _bootstrap_default_org():
    """
    Phase 1 (Chunk 1) — one-time multi-tenancy backfill.

    If no Organization exists yet:
      1. Create a "Default Organization".
      2. Attach every existing user to it (as OrganizationUser rows).
      3. Backfill organization_id on every legacy Company/Contact/Outreach/
         FollowUp/AILog/AuditLog row so they belong to this default tenant.

    Runs on every init_db(), but is a no-op if an Organization already exists.
    Once Chunk 2 makes organization_id required, this remains as a safety net
    for older databases.
    """
    with get_db() as db:
        if db.query(Organization).count() > 0:
            return  # already bootstrapped

        default_org = Organization(name="Default Organization", slug="default", status="active")
        db.add(default_org)
        db.flush()  # get default_org.id

        # Attach every user to the default org, mirroring their global role.
        users = db.query(User).all()
        for u in users:
            db.add(OrganizationUser(
                organization_id=default_org.id,
                user_id=u.id,
                role=u.role or "sales_executive",
                status="active",
            ))

        # Backfill organization_id on all pre-existing tenant rows.
        for model in (Company, Contact, Outreach, FollowUp, AILog, AuditLog):
            db.query(model).filter(model.organization_id.is_(None)).update(
                {model.organization_id: default_org.id},
                synchronize_session=False,
            )

        log.info(
            "Bootstrapped Default Organization (id=%s). Attached %d users, backfilled tenant rows.",
            default_org.id, len(users),
        )


def _seed_admin():
    """Create default super_admin user if no users exist."""
    with get_db() as db:
        if db.query(User).count() == 0:
            import bcrypt as _bcrypt
            admin = User(
                email="admin@braveaspire.com",
                mobile="+91-7981454752",
                password_hash=_bcrypt.hashpw(b"Vikranth@82", _bcrypt.gensalt()).decode(),
                full_name="Super Admin",
                role="super_admin",
                plan="agency",
                is_active=True,
                force_password_change=False,
            )
            db.add(admin)


# ── Session context manager ───────────────────────────────────────────────────

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Demo data seeder ──────────────────────────────────────────────────────────

def seed_demo_data():
    with get_db() as db:
        if db.query(Company).count() > 0:
            return

        companies_data = [
            {"name": "TechNova Solutions",    "website": "technova.io",       "industry": "SaaS",
             "location": "San Francisco, USA","employee_size": 120,"revenue": "$5M-$10M",   "score": 92,
             "status": "Interested","hiring_status": True, "tech_stack": "Python, React, AWS",
             "pain_points": "Scaling engineering team, outdated CI/CD pipeline","source": "AI Discovery"},
            {"name": "HealthBridge Inc",       "website": "healthbridge.com",  "industry": "Healthcare",
             "location": "Austin, USA",       "employee_size": 350,"revenue": "$20M-$50M",  "score": 87,
             "status": "Contacted","hiring_status": True, "tech_stack": "Java, Angular, Azure",
             "pain_points": "Legacy systems integration, HIPAA compliance automation","source": "LinkedIn"},
            {"name": "FinFlow Labs",           "website": "finflowlabs.com",   "industry": "Fintech",
             "location": "New York, USA",     "employee_size": 75, "revenue": "$2M-$5M",    "score": 88,
             "status": "Proposal","hiring_status": True, "tech_stack": "Node.js, Vue.js, GCP",
             "pain_points": "Real-time payment processing, fraud detection system","source": "AI Discovery"},
            {"name": "RetailEdge Co",          "website": "retailedge.co",     "industry": "E-commerce",
             "location": "Chicago, USA",      "employee_size": 200,"revenue": "$10M-$20M",  "score": 79,
             "status": "New",     "hiring_status": False,"tech_stack": "PHP, Magento, MySQL",
             "pain_points": "Outdated ecommerce platform, mobile app needed","source": "Clutch"},
            {"name": "DataSphere Analytics",   "website": "datasphere.ai",     "industry": "Analytics",
             "location": "Seattle, USA",      "employee_size": 95, "revenue": "$3M-$8M",    "score": 85,
             "status": "Won",     "hiring_status": True, "tech_stack": "Python, Spark, Databricks",
             "pain_points": "Data pipeline optimization, ML model deployment","source": "AI Discovery"},
            {"name": "EduTech Global",         "website": "edutechglobal.com", "industry": "EdTech",
             "location": "London, UK",        "employee_size": 180,"revenue": "$8M-$15M",   "score": 81,
             "status": "Contacted","hiring_status": True, "tech_stack": ".NET, React, Azure",
             "pain_points": "Learning management system modernization","source": "AngelList"},
            {"name": "LogiChain Systems",      "website": "logichain.com",     "industry": "Logistics",
             "location": "Dallas, USA",       "employee_size": 450,"revenue": "$30M-$60M",  "score": 74,
             "status": "Lost",    "hiring_status": False,"tech_stack": "Java, Spring Boot, Oracle",
             "pain_points": "Supply chain visibility, route optimization","source": "Manual"},
            {"name": "CyberShield Pro",        "website": "cybershieldpro.com","industry": "Cybersecurity",
             "location": "Washington DC, USA","employee_size": 60, "revenue": "$2M-$4M",    "score": 90,
             "status": "Interested","hiring_status": True,"tech_stack": "Go, Kubernetes, AWS",
             "pain_points": "SOC automation, threat intelligence platform","source": "AI Discovery"},
        ]

        created = []
        for d in companies_data:
            c = Company(**d)
            db.add(c); db.flush()
            created.append(c)

        contacts_raw = [
            ("TechNova Solutions",  "James Carter",  "CTO",                "j.carter@technova.io",         "linkedin.com/in/jamescarter",   True),
            ("TechNova Solutions",  "Sarah Kim",     "VP Engineering",     "s.kim@technova.io",            "linkedin.com/in/sarahkim",      True),
            ("HealthBridge Inc",    "Michael Torres","CEO",                "m.torres@healthbridge.com",    "linkedin.com/in/michaeltorres", True),
            ("HealthBridge Inc",    "Lisa Patel",    "CTO",                "l.patel@healthbridge.com",     "linkedin.com/in/lisapatel",     False),
            ("FinFlow Labs",        "Alex Johnson",  "Founder & CEO",      "alex@finflowlabs.com",         "linkedin.com/in/alexjohnson",   True),
            ("RetailEdge Co",       "Emma Williams", "Engineering Manager","e.williams@retailedge.co",     "linkedin.com/in/emmawilliams",  False),
            ("DataSphere Analytics","David Chen",    "CTO",                "d.chen@datasphere.ai",         "linkedin.com/in/davidchen",     True),
            ("EduTech Global",      "Rachel Green",  "Product Owner",      "r.green@edutechglobal.com",    "linkedin.com/in/rachelgreen",   True),
            ("CyberShield Pro",     "Nathan Brooks", "CEO",                "n.brooks@cybershieldpro.com",  "linkedin.com/in/nathanbrooks",  True),
        ]
        co_map = {c.name: c for c in created}
        created_contacts = []
        for cname, name, desig, email, li, verified in contacts_raw:
            if cname in co_map:
                ct = Contact(company_id=co_map[cname].id, name=name, designation=desig,
                             email=email, linkedin=li, verified=verified)
                db.add(ct); db.flush()
                created_contacts.append(ct)

        outreach_raw = [
            (created_contacts[0],
             "Partnership Opportunity — AI-Powered Engineering Solutions",
             "Hi James,\n\nI came across TechNova Solutions and was impressed by your rapid growth in the SaaS space...\n\nBest,\nBraveAspire Team",
             "Opened", datetime.utcnow()-timedelta(days=5), datetime.utcnow()-timedelta(days=4)),
            (created_contacts[2],
             "Modernizing HealthBridge — HIPAA-Compliant AI Solutions",
             "Hi Michael,\n\nI noticed HealthBridge is expanding its digital health platform...\n\nBest,\nBraveAspire Team",
             "Replied", datetime.utcnow()-timedelta(days=7), datetime.utcnow()-timedelta(days=6)),
            (created_contacts[4],
             "FinFlow — Real-Time Payment Infrastructure We Can Build Together",
             "Hi Alex,\n\nCongratulations on FinFlow Labs' growth!...\n\nBest,\nBraveAspire Team",
             "Sent", datetime.utcnow()-timedelta(days=2), None),
            (created_contacts[8],
             "CyberShield — Automating Your SOC with AI",
             "Hi Nathan,\n\nI saw CyberShield Pro is building next-gen threat intelligence...\n\nBraveAspire Team",
             "Draft", None, None),
        ]

        for ct, subj, body, status, sent_at, opened_at in outreach_raw:
            import uuid as _uuid_mod
            o = Outreach(contact_id=ct.id, subject=subj, body=body, status=status,
                         sent_at=sent_at, opened_at=opened_at,
                         tracking_id=str(_uuid_mod.uuid4()))
            db.add(o); db.flush()
            if status in ("Sent", "Opened", "Replied"):
                for seq, days in {1: 3, 2: 7, 3: 14}.items():
                    sched = (sent_at or datetime.utcnow()) + timedelta(days=days)
                    fu = FollowUp(
                        outreach_id=o.id,
                        subject=f"Re: {subj}",
                        body="Hi,\n\nJust following up on my previous email.\n\nBest,\nBraveAspire Team",
                        sequence_number=seq, scheduled_at=sched,
                        status="Sent" if sched <= datetime.utcnow() else "Scheduled",
                        sent_at=sched if sched <= datetime.utcnow() else None,
                    )
                    db.add(fu)
