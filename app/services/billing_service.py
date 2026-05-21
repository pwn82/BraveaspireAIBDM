"""
Stripe billing service.
Plans: Starter $49/m · Pro $149/m · Agency $499/m
"""
import os
import logging
from typing import Optional

logger = logging.getLogger("billing")

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


def create_checkout_session(plan: str, customer_email: str,
                             success_url: str, cancel_url: str) -> Optional[str]:
    """Create Stripe checkout session. Returns checkout URL."""
    if plan not in PLANS:
        raise ValueError(f"Unknown plan: {plan}")
    if not is_configured():
        raise RuntimeError("STRIPE_SECRET_KEY not set in .env")

    stripe = _stripe()
    plan_info = PLANS[plan]
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
            metadata={"plan": plan},
        )
        return session.url
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        raise


def create_billing_portal(customer_id: str, return_url: str) -> Optional[str]:
    """Open Stripe billing portal for subscription management."""
    stripe = _stripe()
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url
    except Exception as e:
        logger.error(f"Stripe portal error: {e}")
        return None


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Process Stripe webhook — update subscription status in DB."""
    stripe = _stripe()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return {"error": str(e)}

    event_type = event["type"]
    data       = event["data"]["object"]

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(data)
    elif event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
        _handle_subscription_cancelled(data)

    return {"status": "ok", "event": event_type}


def _handle_checkout_completed(session: dict):
    plan            = session.get("metadata", {}).get("plan", "starter")
    customer_email  = session.get("customer_email", "")
    customer_id     = session.get("customer", "")
    subscription_id = session.get("subscription", "")

    from ..database.db import get_db
    from ..database.models import User, Subscription

    with get_db() as db:
        user = db.query(User).filter(User.email == customer_email).first()
        if user:
            user.plan = plan
            sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
            if not sub:
                sub = Subscription(user_id=user.id)
                db.add(sub)
            sub.plan                   = plan
            sub.stripe_customer_id     = customer_id
            sub.stripe_subscription_id = subscription_id
            sub.stripe_session_id      = session.get("id", "")
            sub.status                 = "active"
    logger.info(f"Subscription activated: {customer_email} → {plan}")


def _handle_subscription_updated(sub: dict):
    sub_id = sub.get("id", "")
    status = sub.get("status", "")
    from ..database.db import get_db
    from ..database.models import Subscription
    with get_db() as db:
        s = db.query(Subscription).filter(Subscription.stripe_subscription_id == sub_id).first()
        if s:
            s.status = status


def _handle_subscription_cancelled(sub: dict):
    sub_id = sub.get("id", "") or sub.get("subscription", "")
    from ..database.db import get_db
    from ..database.models import Subscription, User
    with get_db() as db:
        s = db.query(Subscription).filter(Subscription.stripe_subscription_id == sub_id).first()
        if s:
            s.status = "cancelled"
            user = db.query(User).filter(User.id == s.user_id).first()
            if user:
                user.plan = "free"
    logger.info(f"Subscription cancelled: {sub_id}")
