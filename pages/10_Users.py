import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
import pandas as pd
from app.database.db import init_db
from app.services.auth_service import (
    get_all_users, admin_create_user, update_user,
    deactivate_user, reactivate_user, change_password,
    setup_totp, confirm_totp, disable_totp,
)
from app.utils.rbac import require_auth, require_permission, ROLE_DISPLAY, ROLE_DESCRIPTIONS, ROLES
from app.utils.helpers import load_settings

st.set_page_config(page_title="User Management — BraveAspire", page_icon="👥", layout="wide")
_apply_theme()
init_db()
load_settings(st)

# ── Auth guard ────────────────────────────────────────────────────────────────
current_user = require_auth()
require_permission("user.read", current_user)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.pg-title{font-size:1.75rem;font-weight:700;color:#F0EEFF;margin:0}
.pg-sub{font-size:.85rem;color:#9B8FD4;margin:.2rem 0 1.4rem 0;
  padding-bottom:1rem;border-bottom:1px solid #2D2556}
.role-badge{display:inline-block;border-radius:20px;padding:3px 10px;
  font-size:.72rem;font-weight:600;color:#fff}
.rb-super_admin{background:#7C3AED}
.rb-admin{background:#D97706}
.rb-sales_manager{background:#0284C7}
.rb-bdm{background:#0891B2}
.rb-sales_executive{background:#059669}
.rb-viewer{background:#4B5563}
.user-card{background:#1A1830;border:1px solid #2D2556;border-radius:12px;
  padding:1rem 1.2rem;margin-bottom:.8rem}
.stat-chip{background:#12102A;border:1px solid #2D2556;border-radius:8px;
  padding:.5rem 1rem;text-align:center}
.stat-val{font-size:1.5rem;font-weight:800;color:#C4B5FD}
.stat-lbl{font-size:.7rem;color:#9B8FD4;text-transform:uppercase}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="pg-title">👥 User Management</div>', unsafe_allow_html=True)
st.markdown('<div class="pg-sub">Create employees · Assign roles · Manage access · Security settings</div>',
            unsafe_allow_html=True)

# ── Stats row ─────────────────────────────────────────────────────────────────
all_users  = get_all_users()
active_cnt = sum(1 for u in all_users if u["is_active"])
admin_cnt  = sum(1 for u in all_users if u["role"] in ("super_admin", "admin"))

c1, c2, c3, c4 = st.columns(4)
for col, val, lbl in [
    (c1, len(all_users),  "Total Users"),
    (c2, active_cnt,      "Active"),
    (c3, len(all_users) - active_cnt, "Inactive"),
    (c4, admin_cnt,       "Admins"),
]:
    col.markdown(f"""
    <div class="stat-chip">
      <div class="stat-val">{val}</div>
      <div class="stat-lbl">{lbl}</div>
    </div>""", unsafe_allow_html=True)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_list, tab_create, tab_totp = st.tabs(["👥 All Users", "➕ Create User", "🔐 2FA / TOTP"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — User List
# ═══════════════════════════════════════════════════════════════════════════════
with tab_list:
    # Filter bar
    col_s, col_r, col_st = st.columns([3, 2, 2])
    with col_s:
        search_q = st.text_input("🔍 Search by name / email / mobile", key="usr_search")
    with col_r:
        filter_role = st.selectbox("Role", ["All"] + ROLES, key="usr_role_f")
    with col_st:
        filter_active = st.selectbox("Status", ["All", "Active", "Inactive"], key="usr_status_f")

    # Filter
    filtered = all_users
    if search_q:
        q = search_q.lower()
        filtered = [u for u in filtered if
                    q in (u.get("full_name") or "").lower() or
                    q in (u.get("email") or "").lower() or
                    q in (u.get("mobile") or "").lower()]
    if filter_role != "All":
        filtered = [u for u in filtered if u["role"] == filter_role]
    if filter_active == "Active":
        filtered = [u for u in filtered if u["is_active"]]
    elif filter_active == "Inactive":
        filtered = [u for u in filtered if not u["is_active"]]

    if not filtered:
        st.info("No users match your filters.")
    else:
        rows = []
        for u in filtered:
            role = u["role"]
            rows.append({
                "Name":       u.get("full_name") or "—",
                "Email":      u.get("email") or "—",
                "Mobile":     u.get("mobile") or "—",
                "Role":       ROLE_DISPLAY.get(role, role),
                "Department": u.get("department") or "—",
                "Status":     "✅ Active" if u["is_active"] else "❌ Inactive",
                "2FA":        "🔐 ON" if u.get("totp_enabled") else "⚪ OFF",
                "Last Login": u.get("last_login") or "Never",
                "Created":    u.get("created_at") or "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Quick actions ─────────────────────────────────────────────────────────
    if require_permission("user.update", current_user) or True:  # permission checked in action
        st.markdown("**⚡ Quick Actions**")

        user_labels = {
            f"{u.get('full_name','?')} ({u.get('email','?')}) — {ROLE_DISPLAY.get(u['role'], u['role'])}": u
            for u in all_users if u["id"] != current_user["id"]   # can't self-modify
        }

        if not user_labels:
            st.caption("No other users to manage.")
        else:
            sel_label = st.selectbox("Select user to manage", list(user_labels.keys()),
                                      key="qa_user_sel")
            sel_u     = user_labels[sel_label]

            col_a, col_b, col_c, col_d = st.columns(4)

            # Activate / Deactivate
            with col_a:
                if sel_u["is_active"]:
                    if st.button("❌ Deactivate", key="qa_deact",
                                 disabled=not require_permission("user.update", current_user) if False else False):
                        if current_user.get("role") in ("super_admin", "admin"):
                            ok, msg = deactivate_user(sel_u["id"], current_user["id"])
                            st.success(msg) if ok else st.error(msg)
                            st.rerun()
                        else:
                            st.error("Permission denied.")
                else:
                    if st.button("✅ Activate", key="qa_act"):
                        if current_user.get("role") in ("super_admin", "admin"):
                            ok, msg = reactivate_user(sel_u["id"], current_user["id"])
                            st.success(msg) if ok else st.error(msg)
                            st.rerun()
                        else:
                            st.error("Permission denied.")

            # Change role
            with col_b:
                if current_user.get("role") in ("super_admin", "admin"):
                    new_role = st.selectbox("Change role →", ROLES,
                                            index=ROLES.index(sel_u["role"]) if sel_u["role"] in ROLES else 0,
                                            key="qa_role_new")
                    if st.button("💾 Update Role", key="qa_role_btn"):
                        ok, msg = update_user(sel_u["id"], {"role": new_role}, current_user["id"])
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()

            # Reset password
            with col_c:
                if current_user.get("role") in ("super_admin", "admin"):
                    new_pw = st.text_input("New password", type="password", key="qa_pw")
                    if st.button("🔑 Reset Password", key="qa_pw_btn"):
                        if len(new_pw) >= 8:
                            ok, msg = change_password(sel_u["id"], new_pw)
                            st.success(msg) if ok else st.error(msg)
                        else:
                            st.error("Min 8 characters.")

            with col_d:
                st.markdown(f"""
                <div style="font-size:.8rem;color:#9B8FD4;margin-top:1.6rem">
                  <strong style="color:#C4B5FD">{sel_u.get('full_name')}</strong><br>
                  Role: {ROLE_DISPLAY.get(sel_u['role'], sel_u['role'])}<br>
                  Dept: {sel_u.get('department') or 'N/A'}
                </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Create User (Admin only)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_create:
    if current_user.get("role") not in ("super_admin", "admin"):
        st.warning("🚫 Only admins can create user accounts.")
    else:
        st.markdown("""
        <div style="background:#1A1040;border:1px solid #4C1D95;border-radius:10px;
          padding:1rem;margin-bottom:1rem;font-size:.85rem;color:#9B8FD4">
          ℹ️ The new employee will receive a temporary password and must change it on first login.
          If SMTP is configured in <strong>Settings</strong>, credentials are emailed automatically.
        </div>""", unsafe_allow_html=True)

        with st.form("create_user_form", clear_on_submit=True):
            col_n, col_e = st.columns(2)
            with col_n:
                new_name  = st.text_input("Full Name *", placeholder="John Smith")
            with col_e:
                new_email = st.text_input("Email *", placeholder="john@company.com")

            col_m, col_d = st.columns(2)
            with col_m:
                new_mobile = st.text_input("Mobile *", placeholder="+919876543210",
                                           help="Include country code — used as login username")
            with col_d:
                new_dept   = st.text_input("Department", placeholder="Sales, Engineering...")

            col_r, col_p = st.columns(2)
            with col_r:
                new_role = st.selectbox(
                    "Role *",
                    ROLES,
                    index=ROLES.index("sales_executive"),
                    format_func=lambda r: ROLE_DISPLAY.get(r, r),
                )
            with col_p:
                st.markdown(f"""
                <div style="margin-top:.3rem;font-size:.8rem;color:#9B8FD4;line-height:1.5">
                  <strong style="color:#C4B5FD">Role description:</strong><br>
                  {ROLE_DESCRIPTIONS.get(new_role, '')}
                </div>""", unsafe_allow_html=True)

            send_creds = st.checkbox("📧 Email credentials to employee", value=True)

            sub_btn = st.form_submit_button("➕ Create Account", type="primary",
                                             use_container_width=True)

        if sub_btn:
            if not new_name or not new_email or not new_mobile:
                st.error("Full name, email, and mobile are required.")
            else:
                smtp_cfg = None
                if send_creds:
                    smtp_cfg = {k: st.session_state.get(k, "") for k in
                                ["smtp_host", "smtp_port", "smtp_user",
                                 "smtp_password", "from_email", "from_name"]}

                ok, result = admin_create_user(
                    email=new_email.strip(),
                    mobile=new_mobile.strip().replace(" ", ""),
                    full_name=new_name.strip(),
                    role=new_role,
                    department=new_dept.strip(),
                    created_by_id=current_user["id"],
                    smtp_cfg=smtp_cfg if (smtp_cfg and smtp_cfg.get("smtp_host")) else None,
                )

                if ok:
                    temp_pw = result
                    st.success(f"✅ Account created for **{new_name}** ({new_role})")
                    st.markdown(f"""
                    <div style="background:#1A1830;border:1px solid #2D2556;border-radius:8px;
                      padding:1rem;margin:.5rem 0">
                      <div style="color:#9B8FD4;font-size:.82rem;margin-bottom:.3rem">Temporary credentials:</div>
                      <div><strong>Email:</strong> {new_email}</div>
                      <div><strong>Mobile:</strong> {new_mobile}</div>
                      <div><strong>Temp Password:</strong>
                        <code style="color:#F59E0B;font-size:1rem">{temp_pw}</code>
                      </div>
                      <div style="color:#F87171;font-size:.8rem;margin-top:.5rem">
                        ⚠️ Share securely — employee must change password on first login.
                      </div>
                    </div>""", unsafe_allow_html=True)
                    if send_creds and smtp_cfg and smtp_cfg.get("smtp_host"):
                        st.info("📧 Credentials emailed to the employee.")
                    st.rerun()
                else:
                    st.error(f"❌ {result}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — TOTP Setup (for current user)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_totp:
    st.markdown("### 🔐 Two-Factor Authentication (Authenticator App)")
    st.markdown("""
    <div style="background:#1A1830;border:1px solid #2D2556;border-radius:8px;
      padding:.8rem 1rem;font-size:.85rem;color:#9B8FD4;margin-bottom:1rem">
      Link Google Authenticator, Authy, or any TOTP-compatible app.
      Once enabled, you'll need to enter a 6-digit code after OTP login.
    </div>""", unsafe_allow_html=True)

    totp_status = current_user.get("totp_enabled", False)

    if totp_status:
        st.success("✅ Two-factor authentication is **enabled** on your account.")
        if st.button("🗑️ Disable 2FA", type="secondary", key="disable_totp_btn"):
            ok, msg = disable_totp(current_user["id"])
            if ok:
                st.session_state.user["totp_enabled"] = False
                st.success(msg)
                st.rerun()
    else:
        st.warning("⚠️ 2FA is not enabled. We strongly recommend enabling it.")

        if "totp_setup_secret" not in st.session_state:
            if st.button("🔧 Set Up Authenticator App", type="primary", key="setup_totp_btn"):
                secret, qr_b64 = setup_totp(current_user["id"])
                st.session_state["totp_setup_secret"] = secret
                # Store raw bytes so st.image() can render them directly
                if qr_b64:
                    import base64 as _b64
                    st.session_state["totp_setup_qr_bytes"] = _b64.b64decode(qr_b64)
                else:
                    st.session_state["totp_setup_qr_bytes"] = None
                st.rerun()
        else:
            col_qr, col_info = st.columns([1, 2])
            with col_qr:
                st.markdown("**Step 1:** Scan with your app:")
                qr_bytes = st.session_state.get("totp_setup_qr_bytes")
                if qr_bytes:
                    st.image(qr_bytes, width=220,
                             caption="Scan with Google Authenticator / Authy")
                else:
                    # QR image failed — show manual entry fallback
                    st.info("📋 QR unavailable — enter the key manually:")
                    st.code(st.session_state.get("totp_setup_secret", ""), language="text")
                    st.caption("Open your authenticator app → Add account → Enter setup key")

            with col_info:
                st.markdown("**Or enter the secret key manually:**")
                st.code(st.session_state.get("totp_setup_secret", ""), language="text")
                st.markdown("""
                <div style="font-size:.8rem;color:#9B8FD4;line-height:1.6;margin-top:.5rem">
                  <strong style="color:#C4B5FD">How to set up:</strong><br>
                  1. Open <strong>Google Authenticator</strong> or <strong>Authy</strong><br>
                  2. Tap <strong>+</strong> → <em>Scan QR code</em><br>
                  3. Or tap <strong>Enter setup key</strong> and paste the code above<br>
                  4. Enter the 6-digit code below to confirm
                </div>""", unsafe_allow_html=True)

            st.markdown("**Step 2:** Enter the 6-digit code shown in your app to confirm:")
            with st.form("confirm_totp_form"):
                totp_confirm = st.text_input("Confirmation Code", max_chars=6, placeholder="000000")
                totp_ok_btn  = st.form_submit_button("✅ Confirm & Enable 2FA", type="primary",
                                                      use_container_width=True)

            if totp_ok_btn:
                ok, msg = confirm_totp(current_user["id"], totp_confirm.strip())
                if ok:
                    st.session_state.user["totp_enabled"] = True
                    del st.session_state["totp_setup_secret"]
                    st.session_state.pop("totp_setup_qr", None)
                    st.success(f"🎉 {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

            if st.button("Cancel setup", key="cancel_totp_btn"):
                del st.session_state["totp_setup_secret"]
                st.session_state.pop("totp_setup_qr", None)
                st.rerun()

    st.divider()
    st.markdown("### 🔑 Change Your Password")
    with st.form("change_pw_form"):
        cp1 = st.text_input("New Password", type="password")
        cp2 = st.text_input("Confirm Password", type="password")
        cp_btn = st.form_submit_button("Update Password", type="primary", use_container_width=True)

    if cp_btn:
        if cp1 != cp2:
            st.error("Passwords do not match.")
        elif len(cp1) < 8:
            st.error("Minimum 8 characters required.")
        else:
            ok, msg = change_password(current_user["id"], cp1)
            st.success(msg) if ok else st.error(msg)
