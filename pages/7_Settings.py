import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
import pandas as pd
from app.database.db import init_db, seed_demo_data
from app.services.crm_service import CRMService
from app.services.auth_service import get_audit_logs, get_all_users
from app.services.billing_service import is_configured as stripe_configured
from app.utils.helpers import load_settings, get_ai_service, send_email

st.set_page_config(page_title="Settings — BraveAspire", page_icon="⚙️", layout="wide")
_apply_theme()
init_db()
load_settings(st)

from app.utils.rbac import require_auth, require_permission
_current_user = require_auth()
require_permission("settings.read", _current_user)

st.title("⚙️ Settings")
st.caption("Configure AI, email, tracking, billing, and application preferences.")

tabs = st.tabs(["🤖 AI", "📧 Email / SMTP", "📡 Tracking", "💳 Billing Keys",
                "🔑 API Keys", "👤 Profile", "🔒 Security", "🗄️ Database", "📋 Audit Log"])

tab_ai, tab_email, tab_tracking, tab_billing, tab_apikeys, tab_profile, tab_security, tab_db, tab_audit = tabs

# ─── AI ───────────────────────────────────────────────────────────────────────
with tab_ai:
    st.subheader("AI Model Configuration")
    provider = st.radio("Provider", ["ollama", "groq"], horizontal=True,
                         index=0 if st.session_state.get("ai_provider","ollama")=="ollama" else 1,
                         format_func=lambda x: "🖥️ Ollama (Local)" if x=="ollama" else "☁️ Groq (Cloud)")
    st.session_state["ai_provider"] = provider

    st.divider()
    if provider == "ollama":
        c1, c2 = st.columns(2)
        with c1:
            url = st.text_input("Ollama URL", value=st.session_state.get("ollama_url","http://localhost:11434"))
            st.session_state["ollama_url"] = url
        with c2:
            ai_tmp  = get_ai_service(st)
            models  = ai_tmp.list_ollama_models()
            current = st.session_state.get("ollama_model","llama3")
            if models:
                idx = models.index(current) if current in models else 0
                mdl = st.selectbox("Model", models, index=idx)
            else:
                mdl = st.text_input("Model name", value=current)
            st.session_state["ollama_model"] = mdl

        st.info("```\nollama pull llama3\nollama pull mistral\nollama pull deepseek-coder\n```")
    else:
        key = st.text_input("Groq API Key", value=st.session_state.get("groq_api_key",""), type="password",
                              help="console.groq.com")
        st.session_state["groq_api_key"] = key
        _groq_models = [
            "llama-3.3-70b-versatile",   # best quality
            "llama-3.1-8b-instant",      # fastest
            "llama3-8b-8192",
            "mixtral-8x7b-32768",
            "gemma-7b-it",
        ]
        _cur_groq = st.session_state.get("groq_model", "llama-3.3-70b-versatile")
        _groq_idx = _groq_models.index(_cur_groq) if _cur_groq in _groq_models else 0
        mdl = st.selectbox("Model", _groq_models, index=_groq_idx,
                           help="llama-3.3-70b-versatile = best quality | llama-3.1-8b-instant = fastest")
        st.session_state["groq_model"] = mdl

    st.divider()
    col_test, col_save = st.columns(2)
    with col_test:
        if st.button("🔌 Test AI Connection", type="primary"):
            ai = get_ai_service(st)
            with st.spinner("Testing..."):
                ok, msg = ai.is_available()
            (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {msg}")
    with col_save:
        if st.button("💾 Save to .env (persist across restarts)"):
            _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            _lines = []
            if os.path.exists(_env_path):
                with open(_env_path) as _f:
                    _lines = _f.readlines()

            def _set_env(lines, key, value):
                found = False
                result = []
                for ln in lines:
                    if ln.strip().startswith(f"{key}=") or ln.strip().startswith(f"{key} ="):
                        result.append(f"{key}={value}\n")
                        found = True
                    else:
                        result.append(ln)
                if not found:
                    result.append(f"{key}={value}\n")
                return result

            _lines = _set_env(_lines, "AI_PROVIDER",   st.session_state.get("ai_provider","ollama"))
            _lines = _set_env(_lines, "GROQ_API_KEY",  st.session_state.get("groq_api_key",""))
            _lines = _set_env(_lines, "GROQ_MODEL",    st.session_state.get("groq_model","llama3-70b-8192"))
            _lines = _set_env(_lines, "OLLAMA_BASE_URL",st.session_state.get("ollama_url","http://localhost:11434"))
            _lines = _set_env(_lines, "OLLAMA_MODEL",  st.session_state.get("ollama_model","llama3"))
            with open(_env_path, "w") as _f:
                _f.writelines(_lines)
            st.success(f"✅ Saved to {_env_path}")

# ─── Email / SMTP ─────────────────────────────────────────────────────────────
with tab_email:
    st.subheader("Email / SMTP Configuration")
    c1, c2 = st.columns(2)
    with c1:
        smtp_host = st.text_input("SMTP Host",   value=st.session_state.get("smtp_host","smtp.gmail.com"))
        smtp_user = st.text_input("SMTP Email",  value=st.session_state.get("smtp_user",""))
    with c2:
        smtp_port = st.number_input("SMTP Port", value=st.session_state.get("smtp_port",587), step=1)
        smtp_pass = st.text_input("App Password",value=st.session_state.get("smtp_password",""), type="password")

    from_email = st.text_input("From Email", value=st.session_state.get("from_email","") or smtp_user)
    from_name  = st.text_input("From Name",  value=st.session_state.get("from_name","BraveAspire AI BDM"))

    if st.button("Save Email Settings"):
        st.session_state.update({
            "smtp_host":smtp_host,"smtp_port":smtp_port,
            "smtp_user":smtp_user,"smtp_password":smtp_pass,
            "from_email":from_email or smtp_user,"from_name":from_name,
        })
        st.success("Saved!")

    st.info("Gmail: enable 2FA → Google Account → Security → App Passwords → Mail → generate 16-char password")

    c_test, c_imap = st.columns(2)
    with c_test:
        if st.button("Test SMTP"):
            cfg = {"smtp_host":smtp_host,"smtp_port":smtp_port,"smtp_user":smtp_user,
                   "smtp_password":smtp_pass,"from_email":from_email or smtp_user,"from_name":"Test"}
            ok, msg = send_email(smtp_user, "BraveAspire SMTP Test","This is a test.",cfg)
            (st.success if ok else st.error)(msg)

    st.divider()
    st.subheader("IMAP — Inbox Reply Detection")
    c3, c4 = st.columns(2)
    with c3:
        imap_host = st.text_input("IMAP Host",  value=st.session_state.get("imap_host","imap.gmail.com"))
        imap_user = st.text_input("IMAP Email", value=st.session_state.get("imap_user",smtp_user))
    with c4:
        imap_port = st.number_input("IMAP Port", value=st.session_state.get("imap_port",993), step=1)
        imap_pass = st.text_input("IMAP Password",value=st.session_state.get("imap_password",""), type="password")

    if st.button("Save IMAP Settings"):
        st.session_state.update({
            "imap_host":imap_host,"imap_port":int(imap_port),
            "imap_user":imap_user,"imap_password":imap_pass,
        })
        st.success("IMAP settings saved!")

    if st.button("Test IMAP Connection"):
        from app.services.imap_service import IMAPService
        svc = IMAPService(imap_host, int(imap_port), imap_user, imap_pass)
        ok, msg = svc.test_connection()
        (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {msg}")

    if st.button("Check Inbox Now"):
        from app.services.imap_service import IMAPService
        svc   = IMAPService(imap_host, int(imap_port), imap_user, imap_pass)
        count = svc.check_replies()
        st.info(f"Inbox check complete. {count} new replies detected and saved to CRM.")

# ─── Tracking ─────────────────────────────────────────────────────────────────
with tab_tracking:
    st.subheader("Email Open Tracking")
    st.caption("Requires the FastAPI backend to be running (start_backend.bat).")

    tracking_url = st.text_input("Tracking Base URL",
                                  value=st.session_state.get("tracking_base_url","http://localhost:8000"),
                                  help="URL where FastAPI is running. Used for tracking pixels.")
    if st.button("Save Tracking URL"):
        st.session_state["tracking_base_url"] = tracking_url
        st.success("Saved!")

    from app.services.email_tracking_service import get_tracking_stats
    stats = get_tracking_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Opens",  stats["total_opens"])
    c2.metric("Unique Opens", stats["unique_opens"])
    c3.metric("Total Clicks", stats["total_clicks"])

    st.info(f"Pixel URL format: `{tracking_url}/track/open/{{tracking_id}}`\n\n"
            f"Start FastAPI: `uvicorn backend.main:app --port 8000`")

# ─── Billing Keys ─────────────────────────────────────────────────────────────
with tab_billing:
    st.subheader("Stripe API Keys")
    stripe_secret = st.text_input("Stripe Secret Key",
                                   value=st.session_state.get("stripe_secret",""),
                                   type="password", help="sk_live_... or sk_test_...")
    stripe_pub    = st.text_input("Stripe Publishable Key",
                                   value=st.session_state.get("stripe_pub",""),
                                   help="pk_live_... or pk_test_...")
    stripe_hook   = st.text_input("Stripe Webhook Secret",
                                   value=st.session_state.get("stripe_webhook",""),
                                   type="password", help="whsec_...")

    if st.button("Save Stripe Keys"):
        import os
        os.environ["STRIPE_SECRET_KEY"]      = stripe_secret
        os.environ["STRIPE_PUBLISHABLE_KEY"] = stripe_pub
        os.environ["STRIPE_WEBHOOK_SECRET"]  = stripe_hook
        st.session_state.update({"stripe_secret":stripe_secret,"stripe_pub":stripe_pub,"stripe_webhook":stripe_hook})
        st.success("Stripe keys saved to environment!")

    st.divider()
    st.subheader("Hunter.io API Key")
    hunter_key = st.text_input("Hunter.io Key", value=st.session_state.get("hunter_api_key",""), type="password")
    if st.button("Save Hunter Key"):
        os.environ["HUNTER_API_KEY"] = hunter_key
        st.session_state["hunter_api_key"] = hunter_key
        st.success("Saved!")

    st.caption("`hunter.io/api` — used for real email discovery from company domains.")

# ─── API Keys ─────────────────────────────────────────────────────────────────
with tab_apikeys:
    st.subheader("🔑 Lead Scraping API Keys")
    st.caption("Keys are saved to your `.env` file and persist across restarts. "
               "They override environment variables at runtime.")

    def _write_env_keys(env_map: dict):
        """Write a dict of ENV_KEY → value into the .env file."""
        _path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        _lines = []
        if os.path.exists(_path):
            with open(_path) as _fh:
                _lines = _fh.readlines()
        for _k, _v in env_map.items():
            found = False
            new_lines = []
            for ln in _lines:
                if ln.strip().startswith(f"{_k}=") or ln.strip().startswith(f"{_k} ="):
                    new_lines.append(f"{_k}={_v}\n")
                    found = True
                else:
                    new_lines.append(ln)
            if not found:
                new_lines.append(f"{_k}={_v}\n")
            _lines = new_lines
        with open(_path, "w") as _fh:
            _fh.writelines(_lines)
        return _path

    # ── Lead Scraping ──────────────────────────────────────────────────────────
    st.markdown("#### 🏢 Lead Scraping Sources")
    ak_c1, ak_c2 = st.columns(2)
    with ak_c1:
        apollo_key = st.text_input(
            "Apollo.io API Key",
            value=st.session_state.get("apollo_api_key", ""),
            type="password",
            help="[app.apollo.io](https://app.apollo.io) → Settings → Integrations → API Keys",
        )
        google_key = st.text_input(
            "Google Maps API Key",
            value=st.session_state.get("google_maps_api_key", ""),
            type="password",
            help="[console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Places API",
        )
        crunchbase_key = st.text_input(
            "Crunchbase API Key",
            value=st.session_state.get("crunchbase_api_key", ""),
            type="password",
            help="[data.crunchbase.com](https://data.crunchbase.com) → API",
        )
    with ak_c2:
        proxycurl_key = st.text_input(
            "Proxycurl API Key",
            value=st.session_state.get("proxycurl_api_key", ""),
            type="password",
            help="[nubela.co/proxycurl](https://nubela.co/proxycurl) — LinkedIn enrichment",
        )
        apify_token = st.text_input(
            "Apify API Token",
            value=st.session_state.get("apify_api_token", ""),
            type="password",
            help="[apify.com](https://apify.com) → Settings → Integrations → API tokens",
        )
        hunter_key_api = st.text_input(
            "Hunter.io API Key",
            value=st.session_state.get("hunter_api_key", ""),
            type="password",
            help="[hunter.io/api](https://hunter.io/api) — email discovery from company domains",
        )

    st.divider()

    # ── Twilio / SMS / OTP ────────────────────────────────────────────────────
    st.markdown("#### 📱 SMS & OTP (Twilio)")
    tw_c1, tw_c2, tw_c3 = st.columns(3)
    with tw_c1:
        twilio_sid = st.text_input(
            "Twilio Account SID",
            value=st.session_state.get("twilio_account_sid", ""),
            type="password",
            help="console.twilio.com → Account Info",
        )
    with tw_c2:
        twilio_token = st.text_input(
            "Twilio Auth Token",
            value=st.session_state.get("twilio_auth_token", ""),
            type="password",
        )
    with tw_c3:
        twilio_from = st.text_input(
            "Twilio From Number",
            value=st.session_state.get("twilio_from_number", ""),
            placeholder="+1234567890",
            help="E.164 format — your Twilio phone number",
        )

    st.divider()

    _api_save_col, _api_status_col = st.columns([2, 3])

    with _api_save_col:
        if st.button("💾 Save All API Keys", type="primary", key="save_all_api_keys"):
            _updates = {
                "apollo_api_key":      apollo_key,
                "google_maps_api_key": google_key,
                "crunchbase_api_key":  crunchbase_key,
                "proxycurl_api_key":   proxycurl_key,
                "apify_api_token":     apify_token,
                "hunter_api_key":      hunter_key_api,
                "twilio_account_sid":  twilio_sid,
                "twilio_auth_token":   twilio_token,
                "twilio_from_number":  twilio_from,
            }
            st.session_state.update(_updates)

            _env_map = {
                "APOLLO_API_KEY":      apollo_key,
                "GOOGLE_MAPS_API_KEY": google_key,
                "CRUNCHBASE_API_KEY":  crunchbase_key,
                "PROXYCURL_API_KEY":   proxycurl_key,
                "APIFY_API_TOKEN":     apify_token,
                "HUNTER_API_KEY":      hunter_key_api,
                "TWILIO_ACCOUNT_SID":  twilio_sid,
                "TWILIO_AUTH_TOKEN":   twilio_token,
                "TWILIO_FROM_NUMBER":  twilio_from,
            }
            for _k, _v in _env_map.items():
                os.environ[_k] = _v

            _saved_path = _write_env_keys(_env_map)
            st.success(f"✅ All API keys saved to `{os.path.basename(_saved_path)}`")
            st.rerun()

    # ── Status overview ────────────────────────────────────────────────────────
    st.markdown("#### 📊 Configuration Status")
    _status_rows = [
        ("Apollo.io",   apollo_key,     "Company + contact discovery",        "app.apollo.io"),
        ("Google Maps", google_key,     "Local/regional business search",      "console.cloud.google.com"),
        ("Crunchbase",  crunchbase_key, "Startup funding + firmographics",     "data.crunchbase.com"),
        ("Proxycurl",   proxycurl_key,  "LinkedIn company/people enrichment",  "nubela.co/proxycurl"),
        ("Apify",       apify_token,    "Web scraping (Google Maps, LinkedIn, Indeed)", "apify.com"),
        ("Hunter.io",   hunter_key_api, "Email discovery from domains",        "hunter.io"),
        ("Twilio",      twilio_sid,     "SMS OTP delivery",                    "console.twilio.com"),
        ("Clutch.co",   "always",       "IT services scraping (no key needed)", ""),
        ("Indeed",      "always",       "Job posting scraping (no key needed)", ""),
    ]
    for _name, _key_val, _desc, _link in _status_rows:
        _configured = _key_val == "always" or bool(_key_val)
        _c1, _c2, _c3, _c4 = st.columns([0.4, 1.8, 4, 2])
        _c1.markdown("✅" if _configured else "⚙️")
        _c2.markdown(f"**{_name}**")
        _c3.markdown(f"<small>{_desc}</small>", unsafe_allow_html=True)
        if _link and not _configured:
            _c4.markdown(f"[Get key ↗](https://{_link})")
        elif _configured and _key_val != "always":
            _c4.markdown("<small style='color:#34D399'>● Active</small>", unsafe_allow_html=True)

# ─── Profile ──────────────────────────────────────────────────────────────────
with tab_profile:
    st.subheader("Sender / Outreach Profile")
    s_name = st.text_input("Your Name",    value=st.session_state.get("sender_name","BraveAspire Team"))
    s_co   = st.text_input("Your Company", value=st.session_state.get("sender_company","BraveAspire"))
    s_svc  = st.text_area("Services Offered",
                            value=st.session_state.get("services_offered","custom software development & AI solutions"),
                            height=80)
    if st.button("Save Profile"):
        st.session_state.update({"sender_name":s_name,"sender_company":s_co,"services_offered":s_svc})
        st.success("Profile saved!")

# ─── Security ─────────────────────────────────────────────────────────────────
with tab_security:
    st.subheader("Security Settings")
    user = st.session_state.get("user",{})

    if user.get("role") == "admin":
        st.markdown("**All Users**")
        users = get_all_users()
        if users:
            df = pd.DataFrame(users)[["email","full_name","role","plan","is_active","last_login"]]
            df.columns = ["Email","Name","Role","Plan","Active","Last Login"]
            df["Active"] = df["Active"].map({True:"✅",False:"❌"})
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No users found.")
    else:
        st.info("Admin access required to manage users.")

    st.divider()
    st.markdown("**Change Password**")
    with st.form("change_password"):
        old_pass = st.text_input("Current Password", type="password")
        new_pass = st.text_input("New Password", type="password")
        new_pass2= st.text_input("Confirm New Password", type="password")
        if st.form_submit_button("Change Password"):
            if new_pass != new_pass2:
                st.error("Passwords don't match.")
            elif len(new_pass) < 6:
                st.error("Password must be ≥ 6 characters.")
            elif not old_pass:
                st.error("Enter your current password.")
            else:
                from app.services.auth_service import authenticate, hash_password
                from app.database.db import get_db
                from app.database.models import User
                if user:
                    check = authenticate(user.get("email",""), old_pass)
                    if check:
                        with get_db() as db:
                            u = db.query(User).filter(User.id == user["id"]).first()
                            if u:
                                u.password_hash = hash_password(new_pass)
                        st.success("Password changed!")
                    else:
                        st.error("Current password incorrect.")

# ─── Database ─────────────────────────────────────────────────────────────────
with tab_db:
    st.subheader("Database Management")
    crm   = CRMService()
    stats = crm.get_pipeline_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Companies", stats["total_companies"])
    c2.metric("Contacts",  stats["total_contacts"])
    c3.metric("Outreach",  stats["total_outreach"])

    st.divider()
    if st.button("Load Demo Data"):
        seed_demo_data()
        st.success("Demo data loaded!")

    if st.button("Re-index Vector DB"):
        from app.services.vector_service import VectorService
        vs = VectorService()
        if vs.is_available():
            companies = crm.get_companies()
            vs.index_all(companies)
            st.success(f"Indexed {len(companies)} companies in ChromaDB!")
        else:
            st.warning("ChromaDB not available. Install: `pip install chromadb`")

    st.divider()
    st.markdown("**⚠️ Danger Zone**")
    if st.checkbox("I understand — delete ALL data"):
        if st.button("Clear All Data", type="secondary"):
            from app.database.db import engine
            from app.database.models import Base
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            st.success("Database reset complete.")
            st.rerun()

# ─── Audit Log ────────────────────────────────────────────────────────────────
with tab_audit:
    st.subheader("Audit Log")
    user = st.session_state.get("user",{})
    if user.get("role") != "admin":
        st.warning("Admin access required.")
    else:
        limit = st.slider("Show last N entries", 10, 200, 50)
        logs  = get_audit_logs(limit=limit)
        if logs:
            df = pd.DataFrame(logs)[["created_at","user_id","action","resource","details"]]
            df.columns = ["Time","User ID","Action","Resource","Details"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No audit logs yet.")
