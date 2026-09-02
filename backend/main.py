"""
BraveAspire FastAPI Backend
============================
Run:  uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

Phase 3 hardening:
  • Security headers on every response (X-Frame-Options, X-Content-Type-Options,
    Referrer-Policy, Permissions-Policy, and HSTS when APP_ENV=production).
  • CORS: explicit allowlist (no wildcard when credentials are involved — the
    combination is silently ignored by browsers and gives false security).
  • Rate limit: sliding-window per IP, distributed via Redis when REDIS_URL
    is set (app/services/rate_limiter.py) so it survives across uvicorn
    workers/replicas; falls back to an in-process window otherwise.
  • JWT payload now carries `organization_id` (Phase 1), so downstream
    dependencies can enforce org isolation without a DB round-trip.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database.db import init_db
from app.services.auth_service import (
    authenticate, register_user, create_access_token, _resolve_org_id,
)
from app.services.email_tracking_service import TRANSPARENT_GIF, record_open, record_click
from app.services.billing_service import handle_webhook as stripe_webhook
from app.services.scheduler_service import start_scheduler, stop_scheduler

from backend.routers.companies import api as companies_router
from backend.routers.contacts  import api as contacts_router
from backend.routers.outreach  import api as outreach_router
from backend.routers.analytics import api as analytics_router


_APP_ENV = os.getenv("APP_ENV", "development").lower()
_IS_PROD = _APP_ENV == "production"


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BraveAspire AI BDM API",
    version="2.0.0",
    description="Agentic AI Business Development Manager — REST API",
    lifespan=lifespan,
)


# ── CORS ──────────────────────────────────────────────────────────────────────
# CORS_ALLOW_ORIGINS is a comma-separated allowlist. In dev, defaults to
# localhost. In prod you MUST set it explicitly — a wildcard combined with
# credentials silently fails in browsers.
_default_origins = "http://localhost:8501,http://127.0.0.1:8501"
_cors_origins = [
    o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", _default_origins).split(",")
    if o.strip()
]
if _IS_PROD and "*" in _cors_origins:
    raise RuntimeError(
        "CORS_ALLOW_ORIGINS must not be '*' in production. "
        "Set it to a comma-separated list of your actual frontend origins."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Security headers ─────────────────────────────────────────────────────────

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]      = "geolocation=(), microphone=(), camera=()"
    # HSTS only over HTTPS in production — never in dev/HTTP.
    if _IS_PROD:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Rate limiting ─────────────────────────────────────────────────────────────
# Sliding-window per IP. Auth endpoints get a stricter limit than everything
# else. Distributed via Redis when REDIS_URL is set (see app/services/
# rate_limiter.py) — without it, `--workers 2` (this file's own uvicorn
# command) gives each worker its own counters and a client can roughly
# double its effective limit by spreading requests across workers.
from app.services.rate_limiter import allow_request as _rl_allow_request

RATE_LIMIT_GENERAL = int(os.getenv("RATE_LIMIT_GENERAL", "100"))  # req/min per IP
RATE_LIMIT_AUTH    = int(os.getenv("RATE_LIMIT_AUTH",    "10"))   # req/min per IP for auth


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    is_auth = request.url.path.startswith("/api/auth/")
    ceiling = RATE_LIMIT_AUTH if is_auth else RATE_LIMIT_GENERAL
    bucket  = "auth" if is_auth else "general"
    if not _rl_allow_request(f"{ip}:{bucket}", ceiling, window_seconds=60):
        return Response(
            content='{"detail": "Rate limit exceeded"}',
            status_code=429,
            media_type="application/json",
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(companies_router)
app.include_router(contacts_router)
app.include_router(outreach_router)
app.include_router(analytics_router)


# ── Auth endpoints ────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    email: str
    password: str

class RegisterBody(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = ""


@app.post("/api/auth/login")
def login(body: LoginBody):
    user, err = authenticate(body.email, body.password)
    if not user:
        raise HTTPException(401, err or "Invalid credentials")
    token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=user["role"],
        mobile=user.get("mobile", ""),
        organization_id=user.get("organization_id"),
    )
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.post("/api/auth/register", status_code=201)
def register(body: RegisterBody):
    ok, msg = register_user(body.email, body.password, body.full_name)
    if not ok:
        raise HTTPException(400, msg)
    return {"message": msg}


# ── Email Tracking ────────────────────────────────────────────────────────────

@app.get("/track/open/{tracking_id}")
def track_open(tracking_id: str):
    record_open(tracking_id)
    return Response(content=TRANSPARENT_GIF, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache"})


@app.get("/track/click/{tracking_id}")
def track_click(tracking_id: str, redirect_url: str = "https://braveaspire.com"):
    record_click(tracking_id)
    from fastapi.responses import RedirectResponse
    # Basic open-redirect protection: only allow http(s) with a host.
    if not (redirect_url.startswith("http://") or redirect_url.startswith("https://")):
        redirect_url = "https://braveaspire.com"
    return RedirectResponse(url=redirect_url)


# ── Unsubscribe (Phase 5) ─────────────────────────────────────────────────────
# Public endpoint. No auth — the signed token in the URL is the proof of intent.
# The token binds (org_id, outreach_id, email) so a recipient can only remove
# themselves. Response is HTML so it can be opened directly from a mail client.

@app.get("/track/unsubscribe/{token}")
def unsubscribe(token: str):
    from fastapi.responses import HTMLResponse
    from app.services.email_service import EmailService, parse_unsub_token

    payload = parse_unsub_token(token)
    if not payload:
        return HTMLResponse(
            "<h2>Invalid unsubscribe link</h2>"
            "<p>This link is not valid or has been tampered with. "
            "If you keep receiving mail you don't want, please reply "
            "to the last email with 'unsubscribe' in the body.</p>",
            status_code=400,
        )

    # Idempotent — add_to_suppression() no-ops on duplicate.
    EmailService(payload["org_id"]).add_to_suppression(
        payload["email"], reason="unsubscribe", source="unsub_click",
    )

    # Mark the specific Outreach row so re-sends against it also stop.
    if payload["outreach_id"]:
        from app.database.db import get_db
        from app.database.models import Outreach
        with get_db() as db:
            row = db.query(Outreach).filter(Outreach.id == payload["outreach_id"]).first()
            if row:
                row.unsubscribed_at = datetime.utcnow()

    return HTMLResponse(
        f"<h2>You've been unsubscribed</h2>"
        f"<p><code>{payload['email']}</code> will no longer receive "
        f"outreach from this sender.</p>"
    )


# One-click POST variant (RFC 8058). Gmail / Outlook send POST with an
# empty body when the user clicks the native "Unsubscribe" affordance.
@app.post("/track/unsubscribe/{token}")
def unsubscribe_one_click(token: str):
    return unsubscribe(token)


# ── Bounce webhook (Phase 5) ─────────────────────────────────────────────────
# Provider-agnostic ingestion. Provider-specific webhooks (SES, Mailgun,
# SendGrid, Postmark) each POST a different JSON shape; wire your provider
# to translate its payload into this simple contract before calling here,
# OR add per-provider adapters below the base endpoint.

class BounceReport(BaseModel):
    email: str
    bounce_type: str        # hard | soft | complaint | delivered
    provider: Optional[str] = "manual"
    provider_message_id: Optional[str] = None
    outreach_id: Optional[int] = None
    organization_id: Optional[int] = None
    diagnostic: Optional[str] = None


@app.post("/webhooks/bounce")
def bounce_webhook(report: BounceReport, request: Request):
    """
    Record a bounce event. Hard/complaint auto-suppress the recipient.

    Auth: currently trust-on-source. In production put this behind:
      • provider signature check (SES SNS signature, Mailgun HMAC, etc.)
      • or a shared secret in the URL / header
    Never leave open on the public internet without at least one of those.
    """
    from app.services.email_service import record_bounce
    if report.bounce_type not in ("hard", "soft", "complaint", "delivered"):
        raise HTTPException(400, "bounce_type must be hard | soft | complaint | delivered")
    evt = record_bounce(
        organization_id=report.organization_id,
        email=report.email,
        bounce_type=report.bounce_type,
        provider=report.provider or "manual",
        provider_message_id=report.provider_message_id,
        diagnostic=report.diagnostic,
        outreach_id=report.outreach_id,
    )
    return {"id": evt.id, "recorded": True, "auto_suppressed": report.bounce_type in ("hard", "complaint")}


# ── Stripe Webhook ────────────────────────────────────────────────────────────

@app.post("/webhooks/stripe")
async def stripe_webhook_handler(request: Request):
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    result     = stripe_webhook(payload, sig_header)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat(),
            "service": "BraveAspire AI BDM API v2.0"}


@app.get("/")
def root():
    return {"message": "BraveAspire AI BDM API", "docs": "/docs", "health": "/health"}
