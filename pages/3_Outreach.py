import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
import pandas as pd
from datetime import datetime
from app.database.db import init_db
from app.services.crm_service import CRMService
from app.services.email_tracking_service import generate_tracking_id, inject_tracking_pixel
from app.agents.personalization_agent import PersonalizationAgent
from app.agents.followup_agent import FollowUpAgent
from app.agents.proposal_agent import ProposalAgent
from app.utils.helpers import load_settings, get_ai_service, send_email

st.set_page_config(page_title="Outreach — BraveAspire", page_icon="✉️", layout="wide")
_apply_theme()
init_db()
load_settings(st)

from app.utils.rbac import require_auth, require_permission
_current_user = require_auth()
require_permission("outreach.read", _current_user)

crm = CRMService()

# ── CSS (divs/spans — no tables) ──────────────────────────────────────────────
st.markdown("""
<style>
.pg-title{font-size:1.75rem;font-weight:700;color:#F0EEFF;margin:0}
.pg-sub{font-size:.85rem;color:#9B8FD4;margin:.2rem 0 1.2rem 0;
  padding-bottom:1rem;border-bottom:1px solid #2D2556}
.kpi-row{display:flex;gap:1rem;margin-bottom:1.4rem}
.kpi-box{background:linear-gradient(135deg,#1A1830,#12102A);
  border:1px solid #2D2556;border-radius:10px;padding:.8rem 1.2rem;flex:1;
  border-top:3px solid #7C3AED}
.kpi-box.accent{border-top-color:#C084FC}
.kpi-val{font-size:1.4rem;font-weight:800;color:#E2E0F0}
.kpi-lbl{font-size:.7rem;color:#9B8FD4;text-transform:uppercase;letter-spacing:.06em}
.ai-banner{background:linear-gradient(135deg,#1A1040,#12102A);
  border:1px solid #4C1D95;border-radius:12px;padding:1rem 1.4rem;margin-bottom:1.1rem}
.ai-banner-title{font-size:.95rem;font-weight:700;color:#C4B5FD;margin-bottom:.2rem}
.ai-banner-sub{font-size:.82rem;color:#9B8FD4}
.hitl-pending{background:#1E1040;border:1px solid #7C3AED;border-radius:10px;
  padding:.75rem 1.2rem;margin-bottom:1rem;color:#C4B5FD;font-size:.9rem}
.empty-box{text-align:center;padding:3rem;color:#6B7280;
  background:#12102A;border:1px solid #2D2556;border-radius:12px}
.cta-strip{background:#1A1A30;border-left:3px solid #7C3AED;
  padding:.5rem 1rem;border-radius:4px;font-size:.85rem;color:#C4B5FD;margin:.5rem 0}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="pg-title">✉️ Outreach</div>', unsafe_allow_html=True)
st.markdown('<div class="pg-sub">AI-powered personalized outreach · Email · LinkedIn · WhatsApp · Proposals</div>',
            unsafe_allow_html=True)

# ── Stats row ─────────────────────────────────────────────────────────────────
all_out     = crm.get_outreach()
total_out   = len(all_out)
sent_out    = sum(1 for o in all_out if o.get("status") == "Sent")
opened_out  = sum(1 for o in all_out if o.get("status") == "Opened")
replied_out = sum(1 for o in all_out if o.get("status") == "Replied")
pending_out = sum(1 for o in all_out if o.get("status") == "Pending Approval")

st.markdown(f"""
<div class="kpi-row">
  <div class="kpi-box"><div class="kpi-val">{total_out}</div><div class="kpi-lbl">Total Outreach</div></div>
  <div class="kpi-box"><div class="kpi-val">{sent_out}</div><div class="kpi-lbl">Sent</div></div>
  <div class="kpi-box"><div class="kpi-val">{opened_out}</div><div class="kpi-lbl">Opened</div></div>
  <div class="kpi-box"><div class="kpi-val">{replied_out}</div><div class="kpi-lbl">Replied</div></div>
  <div class="kpi-box accent"><div class="kpi-val" style="color:#C084FC">{pending_out}</div><div class="kpi-lbl">Pending Approval</div></div>
</div>""", unsafe_allow_html=True)

# ── Contact selector ──────────────────────────────────────────────────────────
contacts = crm.get_contacts()
if not contacts:
    st.markdown("""
    <div class="empty-box">
      <div style="font-size:2rem">✉️</div>
      <div style="font-size:1rem;font-weight:600;color:#E2E0F0;margin:.5rem 0 .3rem">No contacts yet</div>
      <div>Add contacts in the <strong>Contacts</strong> page first.</div>
    </div>""", unsafe_allow_html=True)
    st.stop()

contact_labels = {f"{c['name']} ({c.get('company_name','?')}) — {c.get('email','')}": c for c in contacts}

col_ct, col_sn, col_sc, col_sv = st.columns([3, 2, 2, 3])
with col_ct:
    selected_label = st.selectbox("Contact", list(contact_labels.keys()),
                                   label_visibility="collapsed", key="out_contact")
with col_sn:
    sender_name    = st.text_input("Your Name",
                                    value=st.session_state.get("sender_name", "BraveAspire Team"),
                                    label_visibility="collapsed", key="s_name", placeholder="Your Name")
with col_sc:
    sender_company = st.text_input("Your Company",
                                    value=st.session_state.get("sender_company", "BraveAspire"),
                                    label_visibility="collapsed", key="s_co", placeholder="Your Company")
with col_sv:
    services       = st.text_input("Services",
                                    value=st.session_state.get("services_offered", "custom software development"),
                                    label_visibility="collapsed", key="s_svc", placeholder="Services you offer")

contact       = contact_labels[selected_label]
companies_all = crm.get_companies()
company       = next((c for c in companies_all if c["id"] == contact.get("company_id")), {})

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_email, tab_li, tab_wa, tab_proposal, tab_list_tab, tab_hitl = st.tabs([
    "📧 Email", "💼 LinkedIn", "💬 WhatsApp", "📄 Proposal",
    "📋 All Outreach", "⏳ Pending Approval",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Email
# ═══════════════════════════════════════════════════════════════════════════════
with tab_email:
    st.markdown("""
    <div class="ai-banner">
      <div class="ai-banner-title">📧 Cold Email Generator</div>
      <div class="ai-banner-sub">AI writes a personalized cold email with a strong hook and clear CTA.</div>
    </div>""", unsafe_allow_html=True)

    col_gen, col_info = st.columns([2, 3])
    with col_info:
        st.info(f"**To:** {contact.get('name','?')} · {contact.get('designation','—')} · **{company.get('name','?')}**")
    with col_gen:
        gen_btn = st.button("✨ Generate AI Email", type="primary", key="gen_email")

    if gen_btn:
        ai    = get_ai_service(st)
        agent = PersonalizationAgent(ai)
        with st.spinner(f"Writing with {ai.provider_label}..."):
            result = agent.generate_email(company=company, contact=contact,
                                           sender_name=sender_name, sender_company=sender_company,
                                           services=services)
        st.session_state["email_draft"] = result
        with st.expander("🧠 Agent Thought Log", expanded=False):
            for step_type, content in result.get("thoughts", []):
                icon = {"THOUGHT": "💭", "ACTION": "⚡", "OBSERVATION": "👁️"}.get(step_type, "•")
                st.markdown(f"**{icon} {step_type}:** {content}")

    if "email_draft" in st.session_state:
        result  = st.session_state["email_draft"]
        st.markdown("**⏳ Human-in-the-Loop Review**")
        subject = st.text_input("Subject line", value=result.get("subject", ""), key="email_subj")
        body    = st.text_area("Email body", value=result.get("body", ""), height=280, key="email_body")

        if result.get("cta"):
            st.markdown(f'<div class="cta-strip"><strong>CTA:</strong> {result.get("cta")}</div>',
                        unsafe_allow_html=True)

        col_send, col_draft, col_regen = st.columns(3)
        with col_send:
            tracking_enabled = st.checkbox("Track opens", value=True, key="track_cb")
            to_email = contact.get("email", "")
            if st.button("✅ Approve & Send", type="primary", disabled=not to_email, key="send_email_btn"):
                tracking_id = generate_tracking_id()
                final_body  = body
                if tracking_enabled:
                    base_url   = st.session_state.get("tracking_base_url", "http://localhost:8000")
                    final_body = inject_tracking_pixel(body, tracking_id, base_url)
                smtp_cfg = {k: st.session_state.get(k) for k in
                            ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "from_email", "from_name"]}
                ok, msg  = send_email(to_email, subject, final_body, smtp_cfg)
                status   = "Sent" if ok else "Draft"
                out_rec  = crm.create_outreach({
                    "contact_id": contact["id"], "subject": subject, "body": body,
                    "status": status, "sent_at": datetime.utcnow() if ok else None,
                    "tracking_id": tracking_id,
                })
                if ok:
                    fu_agent = FollowUpAgent(get_ai_service(st), crm)
                    fu_agent.schedule_followups(out_rec["id"], out_rec, contact, company)
                    st.success(f"✅ Email sent! 3 follow-ups scheduled. Tracking: `{tracking_id}`")
                else:
                    st.warning(f"SMTP not configured — saved as Draft. ({msg})")
                del st.session_state["email_draft"]
        with col_draft:
            if st.button("💾 Save Draft", key="save_draft_btn"):
                crm.create_outreach({"contact_id": contact["id"], "subject": subject,
                                      "body": body, "status": "Draft"})
                st.success("Saved as draft!")
                del st.session_state["email_draft"]
        with col_regen:
            if st.button("🔄 Regenerate", key="regen_email_btn"):
                del st.session_state["email_draft"]
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — LinkedIn
# ═══════════════════════════════════════════════════════════════════════════════
with tab_li:
    st.markdown("""
    <div class="ai-banner">
      <div class="ai-banner-title">💼 LinkedIn Connection Request</div>
      <div class="ai-banner-sub">AI writes a personalized 300-character connection request note.</div>
    </div>""", unsafe_allow_html=True)

    if st.button("✨ Generate LinkedIn Message", type="primary", key="gen_li"):
        ai    = get_ai_service(st)
        agent = PersonalizationAgent(ai)
        with st.spinner("Generating..."):
            msg = agent.generate_linkedin_message(company, contact, sender_name)
        st.session_state["li_message"] = msg

    if "li_message" in st.session_state:
        li_msg = st.text_area("LinkedIn Message", value=st.session_state["li_message"],
                               height=120, key="li_edit")
        char_n = len(li_msg)
        color  = "#34D399" if char_n <= 300 else "#F87171"
        st.caption(f"Characters: {char_n}/300 {'✅' if char_n <= 300 else '⚠️ Too long'}")

        col_info, col_regen = st.columns([3, 1])
        with col_info:
            st.info("📋 Copy this message into LinkedIn's **Add a note** field when connecting.")
        with col_regen:
            if st.button("🔄 Regenerate", key="li_regen"):
                del st.session_state["li_message"]
                st.rerun()

        if st.button("💾 Save to CRM", key="save_li"):
            crm.create_outreach({
                "contact_id":  contact["id"],
                "subject":     f"LinkedIn: {contact.get('name')} @ {company.get('name')}",
                "body":        li_msg,
                "status":      "Sent",
                "sent_at":     datetime.utcnow(),
                "tracking_id": generate_tracking_id(),
            })
            st.success("Saved!")
            del st.session_state["li_message"]

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — WhatsApp
# ═══════════════════════════════════════════════════════════════════════════════
with tab_wa:
    st.markdown("""
    <div class="ai-banner">
      <div class="ai-banner-title">💬 WhatsApp Pitch</div>
      <div class="ai-banner-sub">AI writes a casual, emoji-friendly WhatsApp message (≤500 characters).</div>
    </div>""", unsafe_allow_html=True)

    if st.button("✨ Generate WhatsApp Pitch", type="primary", key="gen_wa"):
        ai    = get_ai_service(st)
        agent = PersonalizationAgent(ai)
        with st.spinner("Generating..."):
            pitch = agent.generate_whatsapp_pitch(company, contact, sender_name)
        st.session_state["wa_pitch"] = pitch

    if "wa_pitch" in st.session_state:
        wa_msg = st.text_area("WhatsApp Message", value=st.session_state["wa_pitch"],
                               height=150, key="wa_edit")
        st.caption(f"Characters: {len(wa_msg)}/500 {'✅' if len(wa_msg) <= 500 else '⚠️ Too long'}")

        col_link, col_regen = st.columns([3, 1])
        with col_link:
            phone = contact.get("phone", "")
            if phone:
                wa_url = (f"https://wa.me/{phone.replace('+','').replace('-','').replace(' ','')}"
                          f"?text={wa_msg[:200]}")
                st.markdown(f"[📱 Open WhatsApp Chat ↗]({wa_url})")
            else:
                st.info("📋 Copy and send via WhatsApp. Add a phone number to this contact for a direct link.")
        with col_regen:
            if st.button("🔄 Regenerate", key="wa_regen"):
                del st.session_state["wa_pitch"]
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Proposal
# ═══════════════════════════════════════════════════════════════════════════════
with tab_proposal:
    st.markdown("""
    <div class="ai-banner">
      <div class="ai-banner-title">📄 Business Proposal Generator</div>
      <div class="ai-banner-sub">AI generates a full proposal with timeline, pricing, and executive summary.</div>
    </div>""", unsafe_allow_html=True)

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        prop_sender = st.text_input("Proposal Author",  value=sender_name,    key="prop_author")
        prop_co     = st.text_input("Your Company",     value=sender_company, key="prop_co")
    with col_p2:
        prop_svc    = st.text_area("Services to Propose", value=services, height=80, key="prop_svc")

    if st.button("✨ Generate Full Proposal", type="primary", key="gen_proposal"):
        ai    = get_ai_service(st)
        agent = ProposalAgent(ai)
        with st.spinner("Generating comprehensive proposal..."):
            result = agent.generate_proposal(company, contact, prop_sender, prop_co, prop_svc)
        st.session_state["proposal_result"] = result

    if "proposal_result" in st.session_state:
        result = st.session_state["proposal_result"]
        st.divider()
        for section, label in [
            ("executive_summary", "📋 Executive Summary"),
            ("problem_statement", "🎯 Problem Statement"),
            ("proposed_solution", "💡 Proposed Solution"),
            ("why_us",            f"⭐ Why {prop_co}?"),
            ("case_study",        "📊 Case Study"),
            ("timeline",          "📅 Project Timeline"),
            ("pricing",           "💰 Pricing"),
            ("next_steps",        "➡️ Next Steps"),
            ("closing",           "🤝 Closing"),
        ]:
            with st.expander(label, expanded=(section == "executive_summary")):
                st.markdown(result.get(section, "—"))

        st.divider()
        col_dl, col_save = st.columns(2)
        with col_dl:
            st.download_button("⬇️ Download Proposal (Markdown)",
                               data=result.get("full_markdown", ""),
                               file_name=f"proposal_{company.get('name','company').replace(' ','_')}.md",
                               mime="text/markdown")
        with col_save:
            if st.button("💾 Save to CRM", key="save_proposal"):
                crm.create_outreach({
                    "contact_id": contact["id"],
                    "subject":    f"Proposal: {company.get('name')}",
                    "body":       result.get("full_markdown", "")[:5000],
                    "status":     "Draft",
                    "tracking_id": generate_tracking_id(),
                })
                st.success("✅ Proposal saved to CRM as Draft!")
                del st.session_state["proposal_result"]

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — All Outreach
# ═══════════════════════════════════════════════════════════════════════════════
with tab_list_tab:
    col_f, col_r = st.columns([4, 1])
    with col_f:
        filter_status = st.selectbox(
            "Filter",
            ["All", "Draft", "Sent", "Opened", "Replied", "Bounced", "Pending Approval"],
            label_visibility="collapsed", key="out_filter",
        )
    with col_r:
        if st.button("↻ Refresh", key="refresh_outreach"):
            st.rerun()

    status_q = "" if filter_status == "All" else filter_status
    rows     = crm.get_outreach(status=status_q)

    if rows:
        STATUS_ICON = {
            "Sent": "📤", "Draft": "📝", "Opened": "👁️",
            "Replied": "💬", "Bounced": "❌", "Pending Approval": "⏳",
        }
        df_rows = []
        for r in rows:
            st_val = r.get("status", "Draft")
            df_rows.append({
                "Company":   r.get("company_name", "—"),
                "Contact":   r.get("contact_name", "—"),
                "Subject":   (r.get("subject") or "—")[:55],
                "Status":    f"{STATUS_ICON.get(st_val,'•')} {st_val}",
                "Sent At":   str(r.get("sent_at", "—") or "—")[:16],
                "Opened At": str(r.get("opened_at", "—") or "—")[:16],
            })
        st.dataframe(pd.DataFrame(df_rows), use_container_width=True, hide_index=True)
        st.caption(f"{len(rows)} records")
    else:
        st.markdown("""
        <div class="empty-box">
          <div style="font-size:2rem">✉️</div>
          <div style="font-size:1rem;font-weight:600;color:#E2E0F0;margin:.5rem 0 .3rem">No outreach yet</div>
          <div>Generate emails in the Email tab and send them.</div>
        </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Pending Approval
# ═══════════════════════════════════════════════════════════════════════════════
with tab_hitl:
    pending = crm.get_outreach(status="Pending Approval")
    if not pending:
        st.success("✅ No emails pending approval — you're all caught up!")
    else:
        st.markdown(f"""
        <div class="hitl-pending">
          ⏳ <strong>{len(pending)}</strong> email(s) awaiting your approval before sending.
        </div>""", unsafe_allow_html=True)

        for item in pending:
            with st.expander(
                f"📧 {item.get('contact_name','?')} @ {item.get('company_name','?')} — {item.get('subject','')}",
                expanded=True,
            ):
                st.text_area("Email Body", value=item.get("body", ""), height=180,
                             disabled=True, key=f"hitl_body_{item['id']}")
                col_a, col_r_col = st.columns(2)
                with col_a:
                    if st.button("✅ Approve & Send", key=f"appr_{item['id']}", type="primary"):
                        smtp_cfg = {k: st.session_state.get(k) for k in
                                    ["smtp_host", "smtp_port", "smtp_user", "smtp_password",
                                     "from_email", "from_name"]}
                        ok, msg  = send_email(
                            item.get("contact_email", ""),
                            item.get("subject", ""),
                            item.get("body", ""),
                            smtp_cfg,
                        )
                        crm.update_outreach(item["id"], {
                            "status": "Sent" if ok else "Draft",
                            "sent_at": datetime.utcnow() if ok else None,
                        })
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()
                with col_r_col:
                    if st.button("❌ Reject", key=f"rej_{item['id']}"):
                        crm.update_outreach(item["id"], {"status": "Draft"})
                        st.info("Moved back to Draft.")
                        st.rerun()
