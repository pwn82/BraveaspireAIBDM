"""
BraveAspire FastAPI Backend
============================
Run:  uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database.db import init_db
from app.services.auth_service import authenticate, register_user, create_token
from app.services.email_tracking_service import TRANSPARENT_GIF, record_open, record_click
from app.services.billing_service import handle_webhook as stripe_webhook
from app.services.scheduler_service import start_scheduler, stop_scheduler

from backend.routers.companies import api as companies_router
from backend.routers.contacts  import api as contacts_router
from backend.routers.outreach  import api as outreach_router
from backend.routers.analytics import api as analytics_router


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Rate limiting (simple in-memory) ─────────────────────────────────────────

from collections import defaultdict
import time as _time

_rate_store: dict = defaultdict(list)
RATE_LIMIT = 100   # requests per minute per IP


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip  = request.client.host if request.client else "unknown"
    now = _time.time()
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < 60]
    if len(_rate_store[ip]) >= RATE_LIMIT:
        return Response("Rate limit exceeded", status_code=429)
    _rate_store[ip].append(now)
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
    user = authenticate(body.email, body.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user["id"], user["email"], user["role"])
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
    return RedirectResponse(url=redirect_url)


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
