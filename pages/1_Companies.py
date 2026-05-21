import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
import pandas as pd
from app.database.db import init_db
from app.services.crm_service import CRMService
from app.agents.lead_discovery_agent import LeadDiscoveryAgent
from app.agents.company_analyzer_agent import CompanyAnalyzerAgent
from app.utils.helpers import load_settings, get_ai_service

st.set_page_config(page_title="Companies — BraveAspire", page_icon="🏢", layout="wide")
_apply_theme()
init_db()
load_settings(st)

from app.utils.rbac import require_auth, require_permission
_current_user = require_auth()
require_permission("company.read", _current_user)

crm = CRMService()

# ── Page-level CSS (divs/spans only — no tables) ─────────────────────────────
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
.empty-box{text-align:center;padding:3rem;color:#6B7280;
  background:#12102A;border:1px solid #2D2556;border-radius:12px}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="pg-title">🏢 Companies</div>', unsafe_allow_html=True)
st.markdown('<div class="pg-sub">Manage your lead pipeline · Discover new companies with AI</div>',
            unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_list, tab_discover, tab_add, tab_analyze = st.tabs(
    ["📋 All Companies", "🔍 AI Discover", "➕ Add Company", "🔬 AI Analyze"]
)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Company List
# ═══════════════════════════════════════════════════════════════════════════════
with tab_list:
    all_cos = crm.get_companies()
    total   = len(all_cos)
    hiring  = sum(1 for c in all_cos if c.get("hiring_status"))
    hot     = sum(1 for c in all_cos if (c.get("score") or 0) >= 85)
    won     = sum(1 for c in all_cos if c.get("status") == "Won")

    st.markdown(f"""
    <div class="kpi-row">
      <div class="kpi-box"><div class="kpi-val">{total}</div><div class="kpi-lbl">Total Companies</div></div>
      <div class="kpi-box"><div class="kpi-val">{hiring}</div><div class="kpi-lbl">Actively Hiring</div></div>
      <div class="kpi-box"><div class="kpi-val">{hot}</div><div class="kpi-lbl">Hot Leads (85+)</div></div>
      <div class="kpi-box"><div class="kpi-val">{won}</div><div class="kpi-lbl">Deals Won</div></div>
    </div>""", unsafe_allow_html=True)

    # Filters
    col_s, col_i, col_l, col_st = st.columns([3, 2, 2, 2])
    with col_s:
        search   = st.text_input("🔍 Search", placeholder="Company name or keyword...",
                                  key="co_search", label_visibility="collapsed")
    with col_i:
        inds     = ["All Industries"] + crm.get_industries()
        industry = st.selectbox("Industry", inds, key="co_ind", label_visibility="collapsed")
    with col_l:
        location = st.text_input("📍 Location", placeholder="Filter by location...",
                                  key="co_loc", label_visibility="collapsed")
    with col_st:
        pipeline_status = st.selectbox(
            "Status",
            ["All Status", "New", "Contacted", "Interested", "Proposal", "Won", "Lost"],
            key="co_status", label_visibility="collapsed",
        )

    ind_q    = "" if industry == "All Industries" else industry
    status_q = "" if pipeline_status == "All Status" else pipeline_status
    companies = crm.get_companies(search=search, industry=ind_q,
                                   location=location, status=status_q)

    if companies:
        # Build display dataframe with emoji formatting
        STATUS_ICON = {
            "New": "🔵", "Contacted": "📤", "Interested": "💚",
            "Proposal": "🟣", "Won": "✅", "Lost": "❌",
        }
        rows = []
        for c in companies:
            sc  = c.get("score") or 0
            rows.append({
                "Company":   c.get("name", "—"),
                "Industry":  c.get("industry") or "—",
                "Location":  c.get("location") or "—",
                "Employees": c.get("employee_size") or "—",
                "Score":     f"🟢 {sc}" if sc >= 85 else (f"🟡 {sc}" if sc >= 70 else f"🔴 {sc}"),
                "Hiring":    "✦ Hiring" if c.get("hiring_status") else "—",
                "Status":    f"{STATUS_ICON.get(c.get('status','New'), '•')} {c.get('status','New')}",
                "Source":    c.get("source") or "Manual",
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"{len(companies)} companies")

        # Status update
        with st.expander("✏️ Update Company Status", expanded=False):
            col_sel, col_new, col_btn = st.columns([3, 2, 1])
            with col_sel:
                sel_name = st.selectbox("Company", [c["name"] for c in companies], key="upd_co_sel")
            with col_new:
                new_st = st.selectbox("New status",
                                       ["New", "Contacted", "Interested", "Proposal", "Won", "Lost"],
                                       key="upd_co_st")
            with col_btn:
                st.write("")
                if st.button("Update", type="primary", key="upd_co_btn"):
                    rec = next((c for c in companies if c["name"] == sel_name), None)
                    if rec:
                        crm.update_company(rec["id"], {"status": new_st})
                        st.success(f"✅ {sel_name} → {new_st}")
                        st.rerun()
    else:
        st.markdown("""
        <div class="empty-box">
          <div style="font-size:2rem;margin-bottom:.5rem">🏢</div>
          <div style="font-size:1rem;font-weight:600;color:#E2E0F0;margin-bottom:.3rem">No companies found</div>
          <div>Use <strong>AI Discover</strong> or <strong>Add Company</strong> to get started.</div>
        </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — AI Discover
# ═══════════════════════════════════════════════════════════════════════════════
with tab_discover:
    st.markdown("""
    <div class="ai-banner">
      <div class="ai-banner-title">🤖 AI Lead Discovery</div>
      <div class="ai-banner-sub">Describe your ideal customer — AI generates a targeted lead list in seconds.</div>
    </div>""", unsafe_allow_html=True)

    col_q, col_c = st.columns([5, 1])
    with col_q:
        query = st.text_input("What companies are you looking for?",
                               placeholder="e.g., SaaS startups using Python that are actively hiring engineers",
                               key="disc_query")
    with col_c:
        count = st.number_input("Count", min_value=3, max_value=15, value=5, key="disc_count")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1: f_industry = st.text_input("Industry", placeholder="Fintech, Healthcare...", key="disc_ind")
    with col_f2: f_location = st.text_input("Location", placeholder="USA, London...", key="disc_loc")
    with col_f3: f_size     = st.text_input("Size", placeholder="50-200 employees", key="disc_size")

    if st.button("🔍 Discover Leads with AI", type="primary", disabled=not query, key="disc_btn"):
        ai     = get_ai_service(st)
        agent  = LeadDiscoveryAgent(ai)
        filters = {k: v for k, v in {
            "industry": f_industry, "location": f_location, "employee_size": f_size
        }.items() if v}

        with st.spinner(f"Searching with {ai.provider_label}..."):
            companies_found, thoughts = agent.discover(query, count=int(count), filters=filters)

        with st.expander("🧠 Agent Thought Log", expanded=False):
            for step_type, content in thoughts:
                icon = {"THOUGHT": "💭", "ACTION": "⚡", "OBSERVATION": "👁️"}.get(step_type, "•")
                st.markdown(f"**{icon} {step_type}:** {content}")

        if companies_found:
            st.success(f"✅ Discovered **{len(companies_found)}** leads!")
            st.session_state["disc_results"] = companies_found
        else:
            st.warning("No leads returned. Try rephrasing your query or check AI in **Settings → AI**.")

    if "disc_results" in st.session_state:
        found = st.session_state["disc_results"]
        rows = []
        for c in found:
            sc = c.get("score", 75) or 75
            rows.append({
                "Company":    c.get("name", "—"),
                "Industry":   c.get("industry") or "—",
                "Location":   c.get("location") or "—",
                "Employees":  c.get("employee_size") or "—",
                "Score":      f"🟢 {sc}" if sc >= 85 else (f"🟡 {sc}" if sc >= 70 else f"🔴 {sc}"),
                "Hiring":     "✦ Hiring" if c.get("hiring_status") else "—",
                "Pain Points": (c.get("pain_points") or "")[:60],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        col_all, col_clr = st.columns([2, 1])
        with col_all:
            if st.button("➕ Add All to CRM", type="primary", key="add_all_disc"):
                for c in found:
                    crm.add_company(c)
                st.success(f"✅ Added {len(found)} companies to CRM!")
                del st.session_state["disc_results"]
                st.rerun()
        with col_clr:
            if st.button("Clear Results", key="clr_disc"):
                del st.session_state["disc_results"]
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Add Manually
# ═══════════════════════════════════════════════════════════════════════════════
with tab_add:
    st.markdown('<div style="font-size:1rem;font-weight:600;color:#C4B5FD;margin-bottom:1rem">➕ Add Company Manually</div>',
                unsafe_allow_html=True)
    with st.form("add_company_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name       = st.text_input("Company Name *", placeholder="ABC Technologies")
            website    = st.text_input("Website", placeholder="abc.com")
            industry   = st.text_input("Industry", placeholder="SaaS, Healthcare...")
            location   = st.text_input("Location", placeholder="New York, USA")
        with c2:
            emp_size   = st.number_input("Employee Size", min_value=0, value=100)
            revenue    = st.text_input("Revenue", placeholder="$5M–$10M")
            score      = st.slider("Lead Score", 0, 100, 75)
            status     = st.selectbox("Status", ["New", "Contacted", "Interested", "Proposal", "Won", "Lost"])

        hiring      = st.checkbox("Actively Hiring")
        tech_stack  = st.text_input("Tech Stack", placeholder="Python, React, AWS")
        pain_points = st.text_area("Pain Points", placeholder="What challenges does this company face?", height=80)
        notes       = st.text_area("Notes", height=60)

        if st.form_submit_button("➕ Add Company", type="primary"):
            if not name:
                st.error("Company name is required.")
            else:
                crm.add_company({
                    "name": name, "website": website, "industry": industry,
                    "location": location, "employee_size": emp_size,
                    "revenue": revenue, "score": score, "status": status,
                    "hiring_status": hiring, "tech_stack": tech_stack,
                    "pain_points": pain_points, "notes": notes, "source": "Manual",
                })
                st.success(f"✅ **{name}** added to CRM!")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — AI Analyze
# ═══════════════════════════════════════════════════════════════════════════════
with tab_analyze:
    st.markdown("""
    <div class="ai-banner">
      <div class="ai-banner-title">🔬 AI Deep Analysis</div>
      <div class="ai-banner-sub">Get opportunity score, pain points, decision-maker strategy, and estimated deal size.</div>
    </div>""", unsafe_allow_html=True)

    companies_all = crm.get_companies()
    if not companies_all:
        st.info("No companies in CRM yet. Add some first.")
    else:
        col_sel, col_btn = st.columns([5, 1])
        with col_sel:
            selected = st.selectbox("Select company to analyze", [c["name"] for c in companies_all], key="analyze_sel")
        with col_btn:
            st.write("")
            analyze_btn = st.button("🔬 Analyze", type="primary", key="analyze_btn")

        company_data = next(c for c in companies_all if c["name"] == selected)

        # Info strip
        col_a, col_b, col_c_col, col_d = st.columns(4)
        col_a.metric("Industry",    company_data.get("industry") or "—")
        col_b.metric("Employees",   company_data.get("employee_size") or "—")
        col_c_col.metric("Score",   f"{company_data.get('score','—')}/100")
        col_d.metric("Status",      company_data.get("status") or "—")

        if analyze_btn:
            ai    = get_ai_service(st)
            agent = CompanyAnalyzerAgent(ai)
            with st.spinner("Analyzing with AI..."):
                result = agent.analyze(company_data)

            if result:
                st.divider()
                m1, m2, m3 = st.columns(3)
                m1.metric("Opportunity Score",  f"{result.get('score','N/A')}/100")
                m2.metric("Urgency",            result.get("urgency", "—"))
                m3.metric("Est. Deal Size",     result.get("estimated_deal_size", "—"))

                col_l, col_r = st.columns(2)
                with col_l:
                    st.markdown("**🎯 Pain Points**")
                    for p in result.get("pain_points", []):
                        st.markdown(f"- {p}")
                    st.markdown(f"**💡 Best Approach:** {result.get('approach_angle','—')}")
                    st.markdown(f"**👤 Decision Maker:** {result.get('decision_maker_title','—')}")
                with col_r:
                    st.markdown("**🛠️ Services to Pitch**")
                    for s in result.get("services_to_pitch", []):
                        st.markdown(f"- {s}")
                    st.markdown(f"**📝 Score Reason:** {result.get('score_reason','—')}")

                new_score = result.get("score")
                if new_score and isinstance(new_score, int):
                    if st.button(f"💾 Save Score ({new_score}) to CRM", type="primary"):
                        crm.update_company(company_data["id"], {"score": new_score})
                        st.success("✅ Score updated!")
