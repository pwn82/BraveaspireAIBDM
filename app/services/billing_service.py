"""
Stripe billing service (Phase 7 hardened).

Plans and their limits live in `entitlements.PLAN_LIMITS`. This module owns
the Stripe integration: checkout sessions, billing portal, webhook processing.

Phase 7 changes:
  • `handle_webhook` is idempotent — every event is fenced by a `stripe_events`
    row on `event_id`, so Stripe's aggressive retries never double-process.
  • Subscription updates now write `Organization.plan` (via user→org lookup),
    matching the multi-tenant model from Phase 1.
  • Missing signature secret returns a clear 400 rather than silently
    accepting unsigned payloads.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger("billing")

# Human-facing plan catalog (name / price / features). Numerical limits live
# in `app.services.entitlements.PLAN_LIMITS` — do not duplicate them here.
PLANS = {
    "starter": {
        "name":       "Starter",
        "price_usd":  49,
        "price_cents":4900,
        "features":   ["500 companies", "100 emails/day", "Basic analytics", "Ollama + Groq AI"],
    },
    "pro": {
        "name":       "Pro",
        "price_usd":  149,
        "price_cents":14900,
        "features":   ["5,000 companies", "500 emails/day", "Advanced analytics",
                       "LangGraph workflows", "Email tracking", "Priority support"],
    },
    "agency": {
        "name":       "Agency",
        "price_usd":  499,
        "price_cents":49900,
        "features":   ["Unlimited companies", "Unlimited emails", "Full analytics",
                       "White labeling", "Multi-user", "API access", "Dedicated support"],
    },
}


def _stripe():
    import stripe as _stripe
    _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
    return _stripe


def is_configured() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY", ""))


# ── Checkout + portal ────────────────────────────────────────────────────────

def create_checkout_session(plan: str, customer_email: str,
                             success_url: str, cancel_url: str,
                             organization_id: Optional[int] = None) -> Optional[str]:
    """Create Stripe checkout session. Returns checkout URL."""
    if plan not in PLANS:
        raise ValueError(f"Unknown plan: {plan}")
    if not is_configured():
        raise RuntimeError("STRIPE_SECRET_KEY not set")

    stripe = _stripe()
    plan_info = PLANS[plan]
    metadata = {"plan": plan}
    if organization_id:
        metadata["organization_id"] = str(organization_id)
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": plan_info["price_cents"],
                    "recurring": {"interval": "month"},
                    "product_data": {
                        "name": f"BraveAspire {plan_info['name']}",
                        "description": ", ".join(plan_info["features"][:3]),
                    },
                },
                "quantity": 1,
            }],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=customer_email,
            metadata=metadata,
            # Stripe subscription objects inherit checkout metadata by default.
            subscription_data={"metadata": metadata},
        )
        return session.url
    except Exception as e:                                              # noqa: BLE001
        logger.error(f"Stripe checkout error: {e}")
        raise


def create_billing_portal(customer_id: str, return_url: str) -> Optional[str]:
    """Open Stripe billing portal for subscription management."""
    stripe = _stripe()
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id, return_url=return_url,
        )
        return session.url
    except Exception as e:                                              # noqa: BLE001
        logger.error(f"Stripe portal error: {e}")
        return None


# ── Webhook ──────────────────────────────────────────────────────────────────

def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Process a Stripe webhook, idempotently.

    Contract:
      1. Verify signature (refuses unsigned unless STRIPE_WEBHOOK_SECRET unset AND
         we're in development mode).
      2. Look up event.id in stripe_events. If present → return no-op success.
      3. Dispatch to per-event-type handler.
      4. Insert row into stripe_events on success (guarded by unique constraint).
    """
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe = _stripe()
    if webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except Exception as e:                                          # noqa: BLE001
            logger.error(f"Stripe webhook signature error: {e}")
            return {"error": str(e)}
    else:
        # Dev-only path — accept unsigned JSON so local testing works.
        if os.getenv("APP_ENV", "development").lower() == "production":
            return {"error": "STRIPE_WEBHOOK_SECRET not configured in production"}
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception as e:                                          # noqa: BLE001
            return {"error": f"invalid payload: {e}"}

    event_id   = event.get("id", "")
    event_type = event.get("type", "")
    data       = event.get("data", {}).get("object", {})

    if not event_id or not event_type:
        return {"error": "missing event id or type"}

    from ..database.db import get_db
    from ..database.models import StripeEvent

    # ── Idempotency fence ────────────────────────────────────────────────
    with get_db() as db:
        prior = db.query(StripeEvent).filter(StripeEvent.event_id == event_id).first()
        if prior:
            logger.info("Stripe event %s already processed — no-op.", event_id)
            return {"status": "ok", "event": event_type, "idempotent": True}

    error: Optional[str] = None
    try:
        if event_type == "checkout.session.completed":
            _handle_checkout_completed(data)
        elif event_type == "customer.subscription.updated":
            _handle_subscription_updated(data)
        elif event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
            _handle_subscription_cancelled(data)
        # Silently accept anything else — presence in stripe_events is proof of receipt.
    except Exception as e:                                              # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
        logger.exception("Stripe handler failure for %s", event_id)

    # Persist the event ledger. Race with a concurrent retry is handled by
    # the unique(event_id) constraint — one wins, the other rolls back.
    try:
        with get_db() as db:
            row = StripeEvent(
                event_id=event_id,
                event_type=event_type,
                status="error" if error else "processed",
                error=error,
                raw_payload=(payload.decode("utf-8", errors="replace")[:20_000]
                             if isinstance(payload, (bytes, bytearray)) else None),
            )
            db.add(row)
    except Exception as e:                                              # noqa: BLE001
        # Duplicate insert from a concurrent worker — that's fine, we're idempotent.
        logger.info("stripe_events insert race for %s: %s", event_id, e)

    if error:
        return {"status": "error", "event": event_type, "error": error}
    return {"status": "ok", "event": event_type, "idempotent": False}


# ── Per-event handlers ───────────────────────────────────────────────────────

def _handle_checkout_completed(session: dict):
    """
    Activate a subscription. Prefers organization_id from metadata; falls back
    to looking up an org via the customer's user → OrganizationUser membership.
    """
    from ..database.db import get_db
    from ..database.models import User, Subscription, Organization, OrganizationUser

    plan            = session.get("metadata", {}).get("plan", "starter")
    org_id_meta     = session.get("metadata", {}).get("organization_id")
    customer_email  = session.get("customer_email", "")
    customer_id     = session.get("customer", "")
    subscription_id = session.get("subscription", "")

    with get_db() as db:
        # 1. Locate the org.
        org: Optional[Organization] = None
        if org_id_meta:
            org = db.query(Organization).filter(
                Organization.id == int(org_id_meta)
            ).first()

        if not org and customer_email:
            user = db.query(User).filter(User.email == customer_email).first()
            if user:
                membership = (
                    db.query(OrganizationUser)
                    .filter(OrganizationUser.user_id == user.id)
                    .filter(OrganizationUser.status == "active")
                    .order_by(OrganizationUser.created_at.asc())
                    .first()
                )
                if membership:
                    org = db.query(Organization).filter(
                        Organization.id == membership.organization_id
                    ).first()

        if not org:
            logger.warning("checkout.session.completed: could not resolve org for %s / meta=%s",
                           customer_email, org_id_meta)
            return

        # 2. Update the org's plan.
        org.plan = plan

        # 3. Upsert Subscription for audit + management.
        sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_id
        ).first() if subscription_id else None
        if sub is None:
            sub = db.query(Subscription).filter(
                Subscription.organization_id == org.id
            ).first()
        if sub is None:
            sub = Subscription(organization_id=org.id)
            db.add(sub)
        sub.organization_id        = org.id
        sub.plan                   = plan
        sub.stripe_customer_id     = customer_id
        sub.stripe_subscription_id = subscription_id
        sub.stripe_session_id      = session.get("id", "")
        sub.status                 = "active"

        # 4. Keep the User.plan mirror in sync (legacy readers still use it).
        if customer_email:
            user = db.query(User).filter(User.email == customer_email).first()
            if user:
                user.plan = plan
                if not sub.user_id:
                    sub.user_id = user.id

        # Snapshot ids while still inside the session — org becomes detached
        # once `with get_db()` exits.
        _org_id_for_log = org.id

    logger.info("Subscription activated: org=%s (%s) → %s",
                _org_id_for_log, customer_email, plan)


def _handle_subscription_updated(sub_payload: dict):
    sub_id = sub_payload.get("id", "")
    status = sub_payload.get("status", "")
    from ..database.db import get_db
    from ..database.models import Subscription
    with get_db() as db:
        s = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == sub_id
        ).first()
        if s:
            s.status = status


def _handle_subscription_cancelled(sub_payload: dict):
    sub_id = sub_payload.get("id", "") or sub_payload.get("subscription", "")
    from ..database.db import get_db
    from ..database.models import Subscription, User, Organization
    with get_db() as db:
        s = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == sub_id
        ).first()
        if not s:
            return
        s.status = "cancelled"
        # Downgrade the org (authoritative) and the user mirror.
        if s.organization_id:
            org = db.query(Organization).filter(Organization.id == s.organization_id).first()
            if org:
                org.plan = "free"
        if s.user_id:
            user = db.query(User).filter(User.id == s.user_id).first()
            if user:
                user.plan = "free"
    logger.info(f"Subscription cancelled: {sub_id}")
