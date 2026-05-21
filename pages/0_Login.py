import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
from app.database.db import init_db
from app.services.auth_service import (
    authenticate, authenticate_with_otp, get_user_by_mobile,
    create_access_token, create_refresh_token, decode_access_token,
    verify_refresh_token, change_password,
)
from app.services.otp_service import create_otp, send_sms_otp, verify_totp
from app.utils.helpers import load_settings

st.set_page_config(page_title="Login — BraveAspire", page_icon="🔐", layout="centered")
_apply_theme()
init_db()
load_settings(st)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.login-wrap{max-width:460px;margin:2rem auto}
.login-logo{text-align:center;margin-bottom:1.5rem}
.login-logo .brand{font-size:1.6rem;font-weight:800;color:#C4B5FD}
.login-logo .sub{font-size:.8rem;color:#9B8FD4;margin-top:.2rem}
.otp-hint{background:#1A1830;border:1px solid #2D2556;border-radius:8px;
  padding:.65rem 1rem;font-size:.82rem;color:#9B8FD4;margin:.5rem 0 1rem 0}
.pw-change-card{background:linear-gradient(135deg,#1A1040,#12102A);
  border:2px solid #7C3AED;border-radius:12px;padding:1.5rem;margin:1rem 0}
.role-chip{display:inline-block;background:#2D2556;border-radius:20px;
  padding:3px 12px;font-size:.75rem;color:#C4B5FD;margin-left:.4rem}
</style>
""", unsafe_allow_html=True)

# ── Already logged in ─────────────────────────────────────────────────────────
if st.session_state.get("authenticated") and st.session_state.get("user"):
    user = st.session_state.user
    role = user.get("role", "")

    # Force password change check
    if user.get("force_password_change"):
        st.markdown("""
        <div class="pw-change-card">
          <h3 style="color:#F59E0B;margin:0 0 .5rem 0">🔑 Password Change Required</h3>
          <p style="color:#9B8FD4;font-size:.85rem">
            For your security, please set a new password before continuing.
          </p>
        </div>""", unsafe_allow_html=True)

        with st.form("force_pw_form"):
            new_pw  = st.text_input("New Password", type="password", help="Min. 8 characters")
            conf_pw = st.text_input("Confirm Password", type="password")
            sub     = st.form_submit_button("Set Password & Continue", type="primary",
                                             use_container_width=True)
        if sub:
            if new_pw != conf_pw:
                st.error("Passwords do not match.")
            elif len(new_pw) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                ok, msg = change_password(user["id"], new_pw)
                if ok:
                    st.session_state.user["force_password_change"] = False
                    st.success("✅ Password set! Continuing...")
                    st.rerun()
                else:
                    st.error(msg)
        st.stop()

    from app.utils.rbac import ROLE_DISPLAY
    role_label = ROLE_DISPLAY.get(role, role)
    st.success(f"✅ Logged in as **{user.get('full_name') or user.get('email')}** "
               f"<span class='role-chip'>{role_label}</span>", unsafe_allow_html=True)
    st.info("Use the sidebar to navigate.")
    if st.button("🚪 Logout", type="secondary"):
        for k in ["authenticated", "user", "token", "refresh_token",
                  "_otp_sent_mobile", "_otp_code_dev", "_otp_step",
                  "_totp_step", "_totp_user_pending"]:
            st.session_state.pop(k, None)
        st.rerun()
    st.stop()

# ── Auto-login from refresh token ─────────────────────────────────────────────
if "refresh_token" in st.session_state:
    user = verify_refresh_token(st.session_state.refresh_token)
    if user:
        token = create_access_token(user["id"], user["email"], user["role"], user.get("mobile",""))
        st.session_state["authenticated"] = True
        st.session_state["user"]          = user
        st.session_state["token"]         = token
        st.rerun()
    else:
        st.session_state.pop("refresh_token", None)

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="login-logo">
  <div class="brand">🤖 BraveAspire</div>
  <div class="sub">AI Business Development Manager</div>
</div>""", unsafe_allow_html=True)

# ── Helper: finish login ──────────────────────────────────────────────────────
def _finish_login(user: dict):
    token = create_access_token(user["id"], user["email"], user["role"],
                                user.get("mobile", ""))
    st.session_state["authenticated"] = True
    st.session_state["user"]          = user
    st.session_state["token"]         = token
    # Clear OTP state
    for k in ["_otp_sent_mobile", "_otp_code_dev", "_otp_step",
              "_totp_step", "_totp_user_pending"]:
        st.session_state.pop(k, None)
    st.success(f"✅ Welcome back, **{user.get('full_name') or user.get('email')}**!")
    st.rerun()


# ── Login mode selector ───────────────────────────────────────────────────────
login_mode = st.radio(
    "Sign in with:",
    ["📱 Mobile OTP (Recommended)", "📧 Email & Password"],
    horizontal=True,
    label_visibility="collapsed",
)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# MODE 1 — Mobile OTP Login
# ═══════════════════════════════════════════════════════════════════════════════
if "📱" in login_mode:

    # Step state: "mobile_entry" → "otp_entry" → "totp_entry"
    if "_otp_step" not in st.session_state:
        st.session_state._otp_step = "mobile_entry"

    # ── Step 1: Enter mobile ──────────────────────────────────────────────────
    if st.session_state._otp_step == "mobile_entry":
        st.markdown("### 📱 Enter your mobile number")
        st.markdown('<div class="otp-hint">Your mobile number is your username. '
                    'An OTP will be sent via SMS.</div>', unsafe_allow_html=True)

        with st.form("mobile_form"):
            mobile = st.text_input("Mobile Number", placeholder="+91 98765 43210",
                                   help="Include country code, e.g. +919876543210")
            sub    = st.form_submit_button("Send OTP →", type="primary", use_container_width=True)

        if sub:
            mobile = mobile.strip().replace(" ", "").replace("-", "")
            if not mobile.startswith("+") or len(mobile) < 10:
                st.error("Please enter a valid mobile number with country code (e.g. +919876543210).")
            else:
                user_chk = get_user_by_mobile(mobile)
                if not user_chk:
                    st.error("Mobile number not found. Contact your admin to create an account.")
                else:
                    ok, code = create_otp(mobile=mobile, purpose="login",
                                          user_id=user_chk["id"])
                    if not ok:
                        st.error(code)
                    else:
                        ok2, msg2 = send_sms_otp(mobile, code)
                        st.session_state._otp_sent_mobile = mobile
                        st.session_state._otp_step        = "otp_entry"
                        if not ok2:
                            # SMS failed — store code for dev fallback display
                            st.session_state._otp_code_dev = code
                            st.warning(f"SMS delivery failed: {msg2}")
                        st.rerun()

    # ── Step 2: Enter OTP ─────────────────────────────────────────────────────
    elif st.session_state._otp_step == "otp_entry":
        mobile_sent = st.session_state.get("_otp_sent_mobile", "")
        st.markdown(f"### 🔑 Enter OTP sent to `{mobile_sent}`")

        dev_code = st.session_state.get("_otp_code_dev")
        if dev_code:
            st.markdown(f"""
            <div class="otp-hint">
              🛠️ <strong>Dev mode</strong> — Twilio not configured.<br>
              Your OTP is: <strong style="color:#C4B5FD;font-size:1.1rem">{dev_code}</strong>
            </div>""", unsafe_allow_html=True)

        with st.form("otp_form"):
            otp_code = st.text_input("6-digit OTP", max_chars=6,
                                      placeholder="______")
            col_verify, col_resend = st.columns([3, 1])
            with col_verify:
                verify_btn = st.form_submit_button("Verify OTP ✓", type="primary",
                                                    use_container_width=True)
            with col_resend:
                resend_btn = st.form_submit_button("Resend", use_container_width=True)

        if verify_btn:
            user, err = authenticate_with_otp(mobile_sent, otp_code.strip())
            if user:
                # Check if TOTP is enabled
                if user.get("totp_enabled"):
                    st.session_state._totp_user_pending = user
                    st.session_state._otp_step          = "totp_entry"
                    st.rerun()
                else:
                    _finish_login(user)
            else:
                st.error(f"❌ {err}")

        if resend_btn:
            for k in ["_otp_step", "_otp_sent_mobile", "_otp_code_dev"]:
                st.session_state.pop(k, None)
            st.rerun()

        if st.button("← Back to mobile entry"):
            for k in ["_otp_step", "_otp_sent_mobile", "_otp_code_dev"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Step 3: TOTP (optional second factor) ─────────────────────────────────
    elif st.session_state._otp_step == "totp_entry":
        st.markdown("### 🔐 Two-Factor Authentication")
        st.info("Open your authenticator app and enter the 6-digit code.")

        with st.form("totp_form"):
            totp_code = st.text_input("Authenticator Code", max_chars=6, placeholder="______")
            totp_btn  = st.form_submit_button("Verify 2FA ✓", type="primary",
                                               use_container_width=True)

        if totp_btn:
            pending_user = st.session_state.get("_totp_user_pending")
            if pending_user:
                from app.database.db import get_db
                from app.database.models import User as _User
                with get_db() as db:
                    u = db.query(_User).filter(_User.id == pending_user["id"]).first()
                    secret = u.totp_secret if u else None

                if secret and verify_totp(secret, totp_code.strip()):
                    _finish_login(pending_user)
                else:
                    st.error("❌ Invalid authenticator code.")

        if st.button("← Back"):
            for k in ["_otp_step", "_totp_user_pending"]:
                st.session_state.pop(k, None)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# MODE 2 — Email + Password
# ═══════════════════════════════════════════════════════════════════════════════
else:
    st.markdown("### 📧 Email & Password Login")
    st.caption("Use your registered email and password.")

    with st.form("email_pw_form"):
        email    = st.text_input("Email", placeholder="admin@braveaspire.com")
        password = st.text_input("Password", type="password")
        remember = st.checkbox("Keep me signed in (7 days)")
        sub      = st.form_submit_button("Sign In →", type="primary", use_container_width=True)

    if sub:
        if not email or not password:
            st.error("Please enter email and password.")
        else:
            user, err = authenticate(email, password)
            if user:
                if remember:
                    rt = create_refresh_token(user["id"])
                    st.session_state["refresh_token"] = rt
                _finish_login(user)
            else:
                st.error(f"❌ {err}")

    st.divider()
    st.caption("🔑 Default super admin: **admin@braveaspire.com** / **Admin@123!**")
    st.caption("ℹ️ New accounts are created by your admin — no public signup available.")
