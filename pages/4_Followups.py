import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.database.db import init_db
from app.services.crm_service import CRMService
from app.agents.followup_agent import FollowUpAgent
from app.utils.helpers import load_settings, get_ai_service, send_email

st.set_page_config(page_title="Follow-ups — BraveAspire", page_icon="🔁", layout="wide")
_apply_theme()
init_db()
load_settings(st)

from app.utils.rbac import require_auth, require_permission
_current_user = require_auth()
require_permission("followup.read", _current_user)

crm = CRMService()

# ── CSS (divs/spans — no tables) ──────────────────────────────────────────────
st.markdown("""
<style>
.pg-title{font-size:1.75rem;font-weight:700;color:#F0EEFF;margin:0}
.pg-sub{font-size:.85rem;color:#9B8FD4;margin:.2rem 0 1.2rem 0;
  padding-bottom:1rem;border-bottom:1px solid #2D2556}
.kpi-row{display:flex;gap:1rem;margin-bottom:1.2rem}
.kpi-box{background:linear-gradient(135deg,#1A1830,#12102A);
  border:1px solid #2D2556;border-radius:10px;padding:.75rem 1.2rem;flex:1;
  border-top:3px solid #7C3AED}
.kpi-box.warn{border-top-color:#F59E0B}
.kpi-box.good{border-top-color:#34D399}
.kpi-val{font-size:1.4rem;font-weight:800;color:#E2E0F0}
.kpi-lbl{font-size:.7rem;color:#9B8FD4;text-transform:uppercase;letter-spacing:.06em}
.overdue-bar{background:#2A1A0A;border:1px solid #92400E;border-radius:10px;
  padding:.8rem 1.2rem;margin-bottom:1.1rem;color:#FCD34D;font-size:.9rem;font-weight:600}
.cadence-note{background:#1A1830;border:1px solid #2D2556;border-radius:8px;
  padding:.65rem 1rem;margin-bottom:1rem;font-size:.83rem;color:#9B8FD4}
.ai-banner{background:linear-gradient(135deg,#1A1040,#12102A);
  border:1px solid #4C1D95;border-radius:12px;padding:1rem 1.4rem;margin-bottom:1.2rem}
.ai-banner-title{font-size:.95rem;font-weight:700;color:#C4B5FD;margin-bottom:.2rem}
.ai-banner-sub{font-size:.82rem;color:#9B8FD4}
.empty-box{text-align:center;padding:3rem;color:#6B7280;
  background:#12102A;border:1px solid #2D2556;border-radius:12px}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="pg-title">🔁 Follow-ups</div>', unsafe_allow_html=True)
st.markdown('<div class="pg-sub">Automated cadence: Day 3 → Day 7 → Day 14 · Smart AI variations per sequence</div>',
            unsafe_allow_html=True)

# ── Stats ─────────────────────────────────────────────────────────────────────
all_fus   = crm.get_followups()
scheduled = [f for f in all_fus if f["status"] == "Scheduled"]
sent_fus  = [f for f in all_fus if f["status"] == "Sent"]
skipped   = [f for f in all_fus if f["status"] == "Skipped"]

st.markdown(f"""
<div class="kpi-row">
  <div class="kpi-box"><div class="kpi-val">{len(all_fus)}</div><div class="kpi-lbl">Total</div></div>
  <div class="kpi-box warn"><div class="kpi-val" style="color:#FBBF24">{len(scheduled)}</div><div class="kpi-lbl">Scheduled</div></div>
  <div class="kpi-box good"><div class="kpi-val" style="color:#34D399">{len(sent_fus)}</div><div class="kpi-lbl">Sent</div></div>
  <div class="kpi-box"><div class="kpi-val" style="color:#6B7280">{len(skipped)}</div><div class="kpi-lbl">Skipped</div></div>
</div>""", unsafe_allow_html=True)

# ── Overdue check ─────────────────────────────────────────────────────────────
ai    = get_ai_service(st)
agent = FollowUpAgent(ai, crm)
overdue = agent.detect_overdue()

if overdue:
    col_warn, col_btn = st.columns([5, 1])
    with col_warn:
        st.markdown(f"""
        <div class="overdue-bar">⚠️ {len(overdue)} follow-up(s) are past due and ready to send</div>
        """, unsafe_allow_html=True)
    with col_btn:
        if st.button("Send All Overdue", type="primary", key="send_overdue"):
            sent_count = 0
            smtp_cfg = {k: st.session_state.get(k) for k in
                        ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "from_email", "from_name"]}
            for fu in overdue:
                to_email = fu.get("contact_email", "")
                if to_email:
                    ok, _ = send_email(to_email, fu.get("subject", "Follow-up"),
                                        fu.get("body", ""), smtp_cfg)
                    if ok:
                        crm.update_followup(fu["id"], {"status": "Sent", "sent_at": datetime.utcnow()})
                        sent_count += 1
            st.success(f"✅ Sent {sent_count} follow-up(s)!")
            st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_sched, tab_sent, tab_ai = st.tabs(["📅 Scheduled", "✅ Sent History", "🤖 AI Follow-up"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Scheduled
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sched:
    st.markdown("""
    <div class="cadence-note">
      📅 <strong>Cadence:</strong> Sequence 1 → Day 3 &nbsp;·&nbsp;
      Sequence 2 → Day 7 &nbsp;·&nbsp; Sequence 3 → Day 14
    </div>""", unsafe_allow_html=True)

    if scheduled:
        rows = []
        for f in scheduled:
            rows.append({
                "Seq":       f"#{f.get('sequence_number', 1)}",
                "Contact":   f.get("contact_name", "?"),
                "Company":   f.get("company_name", "?"),
                "Subject":   (f.get("subject") or "—")[:50],
                "Scheduled": str(f.get("scheduled_at", "—"))[:16],
                "Status":    "📅 Scheduled",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("**Send a specific follow-up now:**")
        fu_labels = {
            f"#{f['sequence_number']} → {f.get('contact_name','?')} @ {f.get('company_name','?')} ({str(f.get('scheduled_at',''))[:10]})": f
            for f in scheduled
        }
        sel_label = st.selectbox("Select follow-up", list(fu_labels.keys()), key="fu_sel")
        sel_fu    = fu_labels[sel_label]

        col_prev, col_send = st.columns([4, 1])
        with col_prev:
            st.text_area("Preview", value=sel_fu.get("body", ""), height=110,
                         disabled=True, key="fu_preview")
        with col_send:
            st.write("")
            st.write("")
            if st.button("📤 Send Now", type="primary", key="send_one_fu"):
                smtp_cfg = {k: st.session_state.get(k) for k in
                            ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "from_email", "from_name"]}
                to_email = sel_fu.get("contact_email", "")
                if not to_email:
                    st.error("No email address for this contact.")
                else:
                    ok, msg = send_email(to_email, sel_fu.get("subject", ""),
                                          sel_fu.get("body", ""), smtp_cfg)
                    if ok:
                        crm.update_followup(sel_fu["id"], {"status": "Sent", "sent_at": datetime.utcnow()})
                        st.success("✅ Sent!")
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        st.markdown("""
        <div class="empty-box">
          <div style="font-size:2rem;margin-bottom:.5rem">📅</div>
          <div style="font-size:1rem;font-weight:600;color:#E2E0F0;margin-bottom:.3rem">No scheduled follow-ups</div>
          <div>Follow-ups are created automatically when you send emails in <strong>Outreach</strong>.</div>
        </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Sent History
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sent:
    if sent_fus:
        rows = []
        for f in sent_fus:
            rows.append({
                "Seq":     f"#{f.get('sequence_number', 1)}",
                "Contact": f.get("contact_name", "?"),
                "Company": f.get("company_name", "?"),
                "Subject": (f.get("subject") or "—")[:50],
                "Sent At": str(f.get("sent_at", "—"))[:16],
                "Status":  "✅ Sent",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"{len(sent_fus)} sent")
    else:
        st.markdown("""
        <div class="empty-box">
          <div style="font-size:2rem;margin-bottom:.5rem">✅</div>
          <div style="font-size:1rem;font-weight:600;color:#E2E0F0;margin-bottom:.3rem">No sent follow-ups yet</div>
          <div>Send scheduled follow-ups to see them here.</div>
        </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — AI Follow-up Generator
# ═══════════════════════════════════════════════════════════════════════════════
with tab_ai:
    st.markdown("""
    <div class="ai-banner">
      <div class="ai-banner-title">🤖 Smart AI Follow-up Writer</div>
      <div class="ai-banner-sub">AI writes a fresh follow-up with a new angle — no copy-paste from the original email.</div>
    </div>""", unsafe_allow_html=True)

    contacts_all = crm.get_contacts()
    if not contacts_all:
        st.warning("⚠️ Add contacts first in the **Contacts** page.")
    else:
        ct_labels = {f"{c['name']} ({c.get('company_name','?')})": c for c in contacts_all}
        col_ct, col_seq = st.columns([4, 1])
        with col_ct:
            sel_ct = st.selectbox("Select Contact", list(ct_labels.keys()), key="ai_fu_ct")
        with col_seq:
            seq = st.selectbox("Sequence", [1, 2, 3], key="ai_fu_seq",
                               format_func=lambda x: f"#{x} Day {[3,7,14][x-1]}")

        ct_sel      = ct_labels[sel_ct]
        cos_all     = crm.get_companies()
        co_sel      = next((c for c in cos_all if c["id"] == ct_sel.get("company_id")), {})
        orig_subj   = st.text_input("Original email subject",
                                     placeholder="Partnership Opportunity...",
                                     key="ai_fu_subj")

        if st.button("✨ Generate AI Follow-up", type="primary",
                     disabled=not orig_subj, key="gen_ai_fu"):
            with st.spinner("Writing smart follow-up..."):
                body = agent.generate_smart_followup(ct_sel, co_sel, seq, orig_subj)
            st.session_state["ai_fu_body"]    = body
            st.session_state["ai_fu_ct_id"]   = ct_sel["id"]
            st.session_state["ai_fu_seq_val"] = seq
            st.session_state["ai_fu_subj_v"]  = orig_subj

        if "ai_fu_body" in st.session_state:
            edited = st.text_area("Generated Follow-up", value=st.session_state["ai_fu_body"],
                                   height=220, key="ai_fu_edit")
            col_save, col_regen = st.columns([3, 1])
            with col_save:
                if st.button("💾 Save as Scheduled", type="primary", key="save_ai_fu"):
                    _ct_id  = st.session_state["ai_fu_ct_id"]
                    _seq_v  = st.session_state["ai_fu_seq_val"]
                    _subj_v = st.session_state["ai_fu_subj_v"]
                    out_list = crm.get_outreach(contact_id=_ct_id)
                    out_id   = out_list[0]["id"] if out_list else None
                    if out_id:
                        days = {1: 3, 2: 7, 3: 14}.get(_seq_v, 3)
                        crm.add_followup({
                            "outreach_id":     out_id,
                            "subject":         f"Re: {_subj_v}",
                            "body":            edited,
                            "sequence_number": _seq_v,
                            "scheduled_at":    datetime.utcnow() + timedelta(days=days),
                            "status":          "Scheduled",
                        })
                        del st.session_state["ai_fu_body"]
                        st.success(f"✅ Follow-up #{_seq_v} saved — scheduled for Day {days}!")
                        st.rerun()
                    else:
                        st.error("No outreach record found for this contact.")
            with col_regen:
                if st.button("🔄 Regenerate", key="regen_ai_fu"):
                    del st.session_state["ai_fu_body"]
                    st.rerun()
