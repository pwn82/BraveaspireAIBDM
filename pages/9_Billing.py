import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
from app.database.db import init_db
from app.services.billing_service import PLANS, is_configured, create_checkout_session
from app.utils.helpers import load_settings

st.set_page_config(page_title="Billing — BraveAspire", page_icon="💳", layout="wide")
_apply_theme()
init_db()
load_settings(st)

st.title("💳 Billing & Subscription")
st.caption("Choose the plan that fits your business. Upgrade or cancel anytime.")

user = st.session_state.get("user", {})
current_plan = user.get("plan", "free")

# ── Current plan banner ───────────────────────────────────────────────────────
plan_colors = {"free": "gray", "starter": "blue", "pro": "purple", "agency": "green"}
plan_emoji  = {"free": "🆓", "starter": "🚀", "pro": "⚡", "agency": "🏢"}
st.info(f"{plan_emoji.get(current_plan,'•')} Current Plan: **{current_plan.upper()}**")

# ── Plan cards ────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Choose Your Plan")

col_s, col_p, col_a = st.columns(3)

for col, plan_key, highlight in [
    (col_s, "starter", False),
    (col_p, "pro",     True),
    (col_a, "agency",  False),
]:
    plan = PLANS[plan_key]
    with col:
        if highlight:
            st.markdown("### ⭐ Most Popular")
        st.markdown(f"## {plan['name']}")
        st.markdown(f"# ${plan['price_usd']}/mo")
        st.divider()
        for feat in plan["features"]:
            st.markdown(f"✅ {feat}")
        st.divider()

        is_current = (current_plan == plan_key)
        btn_label  = "Current Plan" if is_current else f"Upgrade to {plan['name']}"
        btn_type   = "secondary" if is_current else "primary"

        if st.button(btn_label, key=f"btn_{plan_key}",
                      disabled=is_current, type=btn_type, use_container_width=True):
            if not is_configured():
                st.error("Stripe is not configured. Add STRIPE_SECRET_KEY to Settings → Billing.")
            else:
                email = user.get("email","")
                if not email:
                    st.error("Please log in to subscribe.")
                else:
                    try:
                        base = "http://localhost:8501"
                        url  = create_checkout_session(
                            plan_key, email,
                            success_url=f"{base}/Billing?success=true&plan={plan_key}",
                            cancel_url=f"{base}/Billing?cancelled=true",
                        )
                        st.markdown(f"[**Click here to complete payment →**]({url})", unsafe_allow_html=True)
                        st.info("You'll be redirected to Stripe. Return here after payment.")
                    except Exception as e:
                        st.error(f"Error creating checkout: {e}")

# ── Success / cancel feedback ─────────────────────────────────────────────────
query_params = st.query_params
if query_params.get("success"):
    st.success(f"🎉 Subscription activated! You're now on the **{query_params.get('plan','').upper()}** plan.")
if query_params.get("cancelled"):
    st.warning("Payment cancelled. Your plan was not changed.")

# ── Stripe not configured warning ────────────────────────────────────────────
if not is_configured():
    st.divider()
    st.warning("""
⚠️ **Stripe is not configured.**
To enable billing:
1. Go to **Settings → Billing Keys**
2. Add your `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY`
3. Or add them to your `.env` file and restart
""")

# ── Plan comparison table ─────────────────────────────────────────────────────
st.divider()
st.subheader("Feature Comparison")

import pandas as pd
comparison = {
    "Feature":       ["Companies", "Emails/day", "AI Calls/day", "LangGraph Workflows",
                      "Email Tracking", "Multi-user", "Priority Support", "White Labeling"],
    "Free":          ["20","10","50","❌","❌","❌","❌","❌"],
    "Starter ($49)": ["500","100","500","✅","✅","❌","❌","❌"],
    "Pro ($149)":    ["5,000","500","5,000","✅","✅","✅","✅","❌"],
    "Agency ($499)": ["Unlimited","Unlimited","Unlimited","✅","✅","✅","✅","✅"],
}
st.dataframe(pd.DataFrame(comparison), use_container_width=True, hide_index=True)

# ── FAQ ───────────────────────────────────────────────────────────────────────
st.divider()
with st.expander("Frequently Asked Questions"):
    st.markdown("""
**Can I cancel anytime?**
Yes — cancel from your Stripe billing portal. You'll keep access until the period ends.

**Is there a free trial?**
The Free plan gives you limited access to explore the platform.

**What payment methods are accepted?**
All major credit/debit cards via Stripe. Bank transfers available for Agency plan.

**Is my data safe?**
All data is encrypted at rest and in transit. We never share your lead data.
""")
