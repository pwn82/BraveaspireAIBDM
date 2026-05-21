import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
import pandas as pd
import json, re
from app.database.db import init_db
from app.services.crm_service import CRMService
from app.utils.helpers import load_settings, get_ai_service

st.set_page_config(page_title="Contacts — BraveAspire", page_icon="👤", layout="wide")
_apply_theme()
init_db()
load_settings(st)

from app.utils.rbac import require_auth, require_permission
_current_user = require_auth()
require_permission("contact.read", _current_user)

crm = CRMService()

# ── CSS (divs/spans only) ─────────────────────────────────────────────────────
st.markdown("""
<style>
.pg-title{font-size:1.75rem;font-weight:700;color:#F0EEFF;margin:0}
.pg-sub{font-size:.85rem;color:#9B8FD4;margin:.2rem 0 1.2rem 0;
  padding-bottom:1rem;border-bottom:1px solid #2D2556}
.kpi-row{display:flex;gap:1rem;margin-bottom:1.2rem}
.kpi-box{background:linear-gradient(135deg,#1A1830,#12102A);
  border:1px solid #2D2556;border-radius:10px;padding:.75rem 1.2rem;flex:1;
  border-top:3px solid #7C3AED}
.kpi-val{font-size:1.5rem;font-weight:800;color:#E2E0F0}
.kpi-lbl{font-size:.7rem;color:#9B8FD4;text-transform:uppercase;letter-spacing:.06em}
.ai-banner{background:linear-gradient(135deg,#1A1040,#12102A);
  border:1px solid #4C1D95;border-radius:12px;padding:1rem 1.4rem;margin-bottom:1.2rem}
.ai-banner-title{font-size:.95rem;font-weight:700;color:#C4B5FD;margin-bottom:.2rem}
.ai-banner-sub{font-size:.82rem;color:#9B8FD4}
.contact-card{background:#1A1830;border:1px solid #2D2556;border-radius:10px;
  padding:.85rem 1.1rem;margin-bottom:.5rem;display:flex;align-items:center;gap:.9rem}
.avatar{width:38px;height:38px;border-radius:50%;
  background:linear-gradient(135deg,#7C3AED,#4C1D95);
  display:flex;align-items:center;justify-content:center;
  font-size:1rem;font-weight:700;color:white;flex-shrink:0}
.empty-box{text-align:center;padding:3rem;color:#6B7280;
  background:#12102A;border:1px solid #2D2556;border-radius:12px}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="pg-title">👤 Contacts</div>', unsafe_allow_html=True)
st.markdown('<div class="pg-sub">Decision-makers and hiring managers across your pipeline</div>',
            unsafe_allow_html=True)

tab_list, tab_find, tab_add = st.tabs(["📋 All Contacts", "🤖 AI Find Contacts", "➕ Add Contact"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Contact List
# ═══════════════════════════════════════════════════════════════════════════════
with tab_list:
    all_contacts = crm.get_contacts()
    total_c    = len(all_contacts)
    verified_c = sum(1 for c in all_contacts if c.get("verified"))
    with_email = sum(1 for c in all_contacts if c.get("email"))

    st.markdown(f"""
    <div class="kpi-row">
      <div class="kpi-box"><div class="kpi-val">{total_c}</div><div class="kpi-lbl">Total Contacts</div></div>
      <div class="kpi-box"><div class="kpi-val">{verified_c}</div><div class="kpi-lbl">Email Verified</div></div>
      <div class="kpi-box"><div class="kpi-val">{with_email}</div><div class="kpi-lbl">Have Email</div></div>
    </div>""", unsafe_allow_html=True)

    col_s, col_c = st.columns([3, 2])
    with col_s:
        search = st.text_input("🔍 Search", placeholder="Name or email...",
                                key="ct_search", label_visibility="collapsed")
    with col_c:
        companies = crm.get_companies()
        co_opts   = {"All Companies": None}
        co_opts.update({co["name"]: co["id"] for co in companies})
        sel_co    = st.selectbox("Company", list(co_opts.keys()),
                                  key="ct_co_filter", label_visibility="collapsed")
        co_id     = co_opts[sel_co]

    contacts = crm.get_contacts(company_id=co_id, search=search)

    if contacts:
        rows = []
        for c in contacts:
            rows.append({
                "Name":       c.get("name", "—"),
                "Title":      c.get("designation") or "—",
                "Company":    c.get("company_name") or "—",
                "Email":      c.get("email") or "—",
                "Phone":      c.get("phone") or "—",
                "Verified":   "✅ Yes" if c.get("verified") else "—",
                "LinkedIn":   c.get("linkedin") or "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"{len(contacts)} contacts")
    else:
        st.markdown("""
        <div class="empty-box">
          <div style="font-size:2rem;margin-bottom:.5rem">👤</div>
          <div style="font-size:1rem;font-weight:600;color:#E2E0F0;margin-bottom:.3rem">No contacts found</div>
          <div>Use <strong>AI Find Contacts</strong> or <strong>Add Contact</strong> to get started.</div>
        </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — AI Find Contacts
# ═══════════════════════════════════════════════════════════════════════════════
with tab_find:
    st.markdown("""
    <div class="ai-banner">
      <div class="ai-banner-title">🤖 AI Contact Finder</div>
      <div class="ai-banner-sub">AI generates realistic decision-maker profiles for companies in your CRM.</div>
    </div>""", unsafe_allow_html=True)

    companies_all = crm.get_companies()
    if not companies_all:
        st.warning("⚠️ Add companies first in the **Companies** page.")
    else:
        selected_co  = st.selectbox("Select Company", [co["name"] for co in companies_all], key="find_co")
        company_data = next(co for co in companies_all if co["name"] == selected_co)

        roles = st.multiselect(
            "Target Roles",
            ["CTO", "CEO", "Founder", "Engineering Manager", "VP Engineering",
             "Product Owner", "HR Manager", "Head of Growth"],
            default=["CTO", "VP Engineering"],
            key="find_roles",
        )

        if st.button("🤖 Find Contacts with AI", type="primary", disabled=not roles, key="find_btn"):
            ai = get_ai_service(st)
            prompt = f"""Generate {len(roles)} realistic decision-maker contacts for this company:
Company: {company_data['name']}
Industry: {company_data.get('industry', '')}
Size: {company_data.get('employee_size', '')} employees
Website: {company_data.get('website', '')}
Roles needed: {', '.join(roles)}

Return a JSON array:
[{{"name": "Full Name", "designation": "Title", "email": "email@domain.com", "linkedin": "linkedin.com/in/handle", "phone": "+1-555-0000"}}]
Only JSON, no markdown."""

            with st.spinner(f"Generating with {ai.provider_label}..."):
                raw       = ai.generate(prompt)
                raw_clean = re.sub(r"```(?:json)?", "", raw).strip()
                try:
                    cts = json.loads(raw_clean)
                    if not isinstance(cts, list):
                        raise ValueError
                except Exception:
                    match = re.search(r"\[.*\]", raw_clean, re.DOTALL)
                    cts = json.loads(match.group()) if match else []

            if cts:
                st.success(f"✅ Found **{len(cts)}** contacts!")
                # Show as cards using st.markdown divs (no tables)
                for ct in cts:
                    initial = (ct.get("name") or "?")[0].upper()
                    st.markdown(f"""
                    <div class="contact-card">
                      <div class="avatar">{initial}</div>
                      <div style="flex:1">
                        <div style="font-weight:600;color:#E2E0F0">{ct.get('name','?')}</div>
                        <div style="font-size:.8rem;color:#9B8FD4">{ct.get('designation','—')}</div>
                        <div style="font-size:.8rem;color:#7C3AED">{ct.get('email','—')}</div>
                      </div>
                      <div style="font-size:.8rem;color:#6B7280">{ct.get('phone','—')}</div>
                    </div>""", unsafe_allow_html=True)

                st.session_state["found_contacts"]   = cts
                st.session_state["found_company_id"] = company_data["id"]
            else:
                st.warning("Could not parse contacts. Check AI in **Settings → AI**.")

        if (st.session_state.get("found_contacts")
                and st.session_state.get("found_company_id") == company_data["id"]):
            if st.button("➕ Add All to CRM", type="primary", key="add_all_cts"):
                for ct in st.session_state["found_contacts"]:
                    crm.add_contact({
                        "company_id":  company_data["id"],
                        "name":        ct.get("name", "Unknown"),
                        "designation": ct.get("designation", ""),
                        "email":       ct.get("email", ""),
                        "linkedin":    ct.get("linkedin", ""),
                        "phone":       ct.get("phone", ""),
                        "verified":    False,
                    })
                st.success("✅ Contacts added to CRM!")
                del st.session_state["found_contacts"]
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Add Contact
# ═══════════════════════════════════════════════════════════════════════════════
with tab_add:
    st.markdown('<div style="font-size:1rem;font-weight:600;color:#C4B5FD;margin-bottom:1rem">➕ Add Contact Manually</div>',
                unsafe_allow_html=True)
    with st.form("add_contact_form", clear_on_submit=True):
        companies_all2 = crm.get_companies()
        co_map = {co["name"]: co["id"] for co in companies_all2}

        if not co_map:
            st.warning("No companies found — add companies first.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                co_sel      = st.selectbox("Company *", list(co_map.keys()))
                name        = st.text_input("Full Name *", placeholder="Jane Smith")
                designation = st.text_input("Job Title", placeholder="CTO, VP Engineering...")
            with c2:
                email    = st.text_input("Email Address", placeholder="jane@company.com")
                phone    = st.text_input("Phone", placeholder="+1-555-0100")
                linkedin = st.text_input("LinkedIn URL", placeholder="linkedin.com/in/janesmith")

            verified = st.checkbox("Email Verified")
            notes    = st.text_area("Notes", height=60)

            if st.form_submit_button("➕ Add Contact", type="primary"):
                if not name or not co_sel:
                    st.error("Name and company are required.")
                else:
                    crm.add_contact({
                        "company_id":  co_map[co_sel],
                        "name":        name,
                        "designation": designation,
                        "email":       email,
                        "phone":       phone,
                        "linkedin":    linkedin,
                        "verified":    verified,
                        "notes":       notes,
                    })
                    st.success(f"✅ **{name}** added!")
