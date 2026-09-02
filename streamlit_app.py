import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from app.database.db import init_db, seed_demo_data
from app.utils.helpers import load_settings, status_emoji, get_scoped_crm
from app.utils.theme import apply_theme as _apply_theme

st.set_page_config(
    page_title="BraveAspire AI BDM",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)
_apply_theme()

init_db()
load_settings(st)

# ── Auth guard ────────────────────────────────────────────────────────────────
def require_auth():
    if not st.session_state.get("authenticated"):
        st.markdown("""
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;min-height:70vh;gap:8px;">
          <div style="width:56px;height:56px;background:linear-gradient(135deg,#7C3AED,#5B21B6);
                      border-radius:16px;display:flex;align-items:center;justify-content:center;
                      font-size:1.8rem;box-shadow:0 8px 24px rgba(124,58,237,0.4);margin-bottom:8px;">🤖</div>
          <h2 style="color:#EDE9FE;font-weight:800;font-size:1.6rem;margin:0;">BraveAspire AI BDM</h2>
          <p style="color:#8B80C4;font-size:0.9rem;margin:0 0 24px;">
            Agentic B2B Sales Intelligence Platform
          </p>
        </div>
        """, unsafe_allow_html=True)
        col_login, _ = st.columns([1, 2])
        with col_login:
            with st.form("quick_login"):
                email    = st.text_input("Email", value="admin@braveaspire.com")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Sign In", type="primary", use_container_width=True):
                    from app.services.auth_service import authenticate, create_access_token
                    user, err = authenticate(email, password)
                    if user:
                        token = create_access_token(user["id"], user["email"], user["role"])
                        st.session_state.update({"authenticated": True, "user": user, "token": token})
                        st.rerun()
                    else:
                        st.error(err or "Invalid credentials. Default: admin@braveaspire.com / Admin@123!")
            st.caption("Or go to **Login** page in the sidebar.")
        st.stop()

require_auth()

# ── Sidebar ───────────────────────────────────────────────────────────────────
user = st.session_state.get("user", {})
with st.sidebar:
    st.markdown("""
    <div style="padding:14px 6px 12px;border-bottom:1px solid #2D2556;margin-bottom:14px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="width:38px;height:38px;background:linear-gradient(135deg,#7C3AED,#5B21B6);
                    border-radius:10px;display:flex;align-items:center;justify-content:center;
                    font-size:1.2rem;box-shadow:0 4px 12px rgba(124,58,237,0.4);">🤖</div>
        <div>
          <div style="font-weight:800;font-size:1rem;color:#EDE9FE;line-height:1.2;">BraveAspire</div>
          <div style="font-size:0.68rem;color:#8B80C4;letter-spacing:0.1em;font-weight:600;">AI BDM AGENT</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    provider  = st.session_state.get("ai_provider", "ollama").upper()
    plan      = user.get("plan", "free")
    plan_color = {"free":"#8B80C4","starter":"#60A5FA","pro":"#A78BFA","agency":"#34D399"}.get(plan,"#8B80C4")
    st.markdown(f"""
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
      <span style="background:rgba(124,58,237,0.15);border:1px solid rgba(124,58,237,0.35);
                   border-radius:20px;padding:3px 10px;font-size:0.7rem;color:#C4B5FD;font-weight:500;">
        ⚡ {provider}
      </span>
      <span style="background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.3);
                   border-radius:20px;padding:3px 10px;font-size:0.7rem;color:{plan_color};font-weight:700;">
        {plan.upper()}
      </span>
    </div>
    <div style="font-size:0.72rem;color:#7B6EA8;margin-bottom:16px;overflow:hidden;
                text-overflow:ellipsis;white-space:nowrap;">{user.get('email','—')}</div>
    """, unsafe_allow_html=True)

    from app.utils.rbac import ROLE_DISPLAY, has_permission, get_current_org_id
    role       = user.get("role", "viewer")
    role_label = ROLE_DISPLAY.get(role, role)
    st.markdown(f'<div style="font-size:.72rem;color:#7C3AED;margin-bottom:8px">{role_label}</div>',
                unsafe_allow_html=True)

    st.page_link("streamlit_app.py",     label="Dashboard",   icon="📊")
    if has_permission(user, "company.read"):
        st.page_link("pages/1_Companies.py", label="Companies",   icon="🏢")
    if has_permission(user, "contact.read"):
        st.page_link("pages/2_Contacts.py",  label="Contacts",    icon="👤")
    if has_permission(user, "outreach.read"):
        st.page_link("pages/3_Outreach.py",  label="Outreach",    icon="✉️")
    if has_permission(user, "followup.read"):
        st.page_link("pages/4_Followups.py", label="Follow-ups",  icon="🔁")
    if has_permission(user, "analytics.read"):
        st.page_link("pages/5_Analytics.py", label="Analytics",   icon="📈")
    if has_permission(user, "ai_chat.use"):
        st.page_link("pages/6_AI_Chat.py",   label="AI Chat",     icon="💬")
    if has_permission(user, "workflow.run"):
        st.page_link("pages/8_Workflow.py",  label="AI Workflow", icon="🔄")
    if has_permission(user, "scraping.run"):
        st.page_link("pages/9_Lead_Scraper.py", label="Lead Scraper", icon="🔎")
    if has_permission(user, "settings.read"):
        st.page_link("pages/7_Settings.py",  label="Settings",    icon="⚙️")
    if user.get("role") in ("super_admin", "admin"):
        st.page_link("pages/10_Users.py",    label="User Management", icon="👥")
    # Billing — always show
    st.page_link("pages/9_Billing.py",   label="Billing",     icon="💳")

    st.divider()
    with st.expander("⚡ Quick Actions"):
        if st.button("Load Demo Data", use_container_width=True):
            seed_demo_data(organization_id=get_current_org_id())
            st.success("Demo data loaded!"); st.rerun()
        if st.button("Logout", use_container_width=True):
            for k in ["authenticated","user","token"]: st.session_state.pop(k, None)
            st.rerun()

# ── Dashboard data ────────────────────────────────────────────────────────────
crm    = get_scoped_crm(st)
org_id = crm.organization_id
stats  = crm.get_pipeline_stats()
hour   = datetime.now().hour
greet  = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
name   = user.get("full_name", user.get("email","").split("@")[0]).title()

from app.services.dashboard_service import kpi_sparklines
from app.services.activity_service import recent_activities, humanize_delta
from app.services.insights_service import compute_insights
from app.services.task_service import TaskService
from app.utils.ui_components import kpi_card

sparklines = kpi_sparklines(org_id)
task_svc   = TaskService(org_id)


# ── Top bar: search · notifications · date range · quick add ─────────────────
pending_approval = len(crm.get_outreach(status="Pending Approval"))
open_tasks_count = len(task_svc.list_open(limit=50))
notif_count = pending_approval + open_tasks_count

tb_search, tb_bell, tb_dates, tb_add = st.columns([5, 1, 2.2, 1.6])
with tb_search:
    st.text_input("Search", placeholder="🔍  Search companies, contacts, emails...",
                  label_visibility="collapsed", key="dash_search")
with tb_bell:
    with st.popover(f"🔔 {notif_count}" if notif_count else "🔔"):
        st.markdown("**Needs your attention**")
        if pending_approval:
            st.markdown(f"⏳ {pending_approval} outreach message(s) awaiting approval")
        if open_tasks_count:
            st.markdown(f"✅ {open_tasks_count} open task(s)")
        if not notif_count:
            st.caption("You're all caught up.")
with tb_dates:
    st.markdown(f"""
    <div style="background:#14112E;border:1px solid #2D2556;border-radius:8px;
                padding:8px 14px;font-size:0.8rem;color:#C4B5FD;text-align:center;
                white-space:nowrap;">
      📅 {datetime.now().strftime('%b %d')} – {datetime.now().strftime('%b %d, %Y')}
    </div>""", unsafe_allow_html=True)
with tb_add:
    with st.popover("➕ Add New", use_container_width=True):
        if st.button("🏢 Company", use_container_width=True):
            st.switch_page("pages/1_Companies.py")
        if st.button("👤 Contact", use_container_width=True):
            st.switch_page("pages/2_Contacts.py")
        if st.button("✉️ Outreach", use_container_width=True):
            st.switch_page("pages/3_Outreach.py")
        st.divider()
        with st.form("dash_quick_task", clear_on_submit=True):
            qt_title = st.text_input("Quick task", placeholder="Follow up with...")
            qt_priority = st.selectbox("Priority", ["low", "medium", "high"], index=1)
            if st.form_submit_button("Add task", use_container_width=True) and qt_title:
                task_svc.create({"title": qt_title, "priority": qt_priority,
                                 "created_by_id": user.get("id"), "assigned_to_id": user.get("id")})
                st.rerun()

# Header
st.markdown(f"""
<div style="display:flex;align-items:flex-start;justify-content:space-between;
            margin:20px 0 28px;padding-bottom:20px;border-bottom:1px solid #1E1B4B;">
  <div>
    <h1 style="margin:0;font-size:1.75rem;font-weight:800;color:#EDE9FE;">
      {greet}, {name} 👋
    </h1>
    <p style="margin:4px 0 0;color:#8B80C4;font-size:0.875rem;">
      Here's what's happening with your pipeline today.
    </p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── KPI Cards (with real 7-day sparklines) ────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
active = stats["pipeline"].get("Interested",0) + stats["pipeline"].get("Proposal",0)


reply_rate_spark = [
    (r / s * 100 if s else 0) for r, s in zip(sparklines["replies"], sparklines["emails_sent"])
]
with k1: kpi_card(k1, "Total Companies", f"{stats['total_companies']:,}", 11.3,
                  spark=sparklines["companies"])
with k2: kpi_card(k2, "Verified Contacts", f"{stats['total_contacts']:,}", 8.2,
                  color="#A855F7", spark=sparklines["verified_contacts"])
with k3: kpi_card(k3, "Emails Sent", f"{stats['emails_sent']:,}", 15.3,
                  color="#6366F1", spark=sparklines["emails_sent"])
with k4: kpi_card(k4, "Reply Rate", f"{stats['reply_rate']}%", round(stats['reply_rate']-5,1),
                  color="#8B5CF6", spark=reply_rate_spark)
with k5: kpi_card(k5, "Active Leads", f"{active:,}", 3.2, delta_label="vs last week",
                  color="#7C3AED", spark=sparklines["companies"])

st.markdown("<div style='margin-bottom:24px'></div>", unsafe_allow_html=True)

# ── Pipeline Overview + Email Funnel ──────────────────────────────────────────
left, right = st.columns([5, 4])

with left:
    st.markdown('<div style="font-weight:700;font-size:1rem;color:#DDD6FE;margin-bottom:12px;">Pipeline Overview</div>', unsafe_allow_html=True)
    pipeline = stats["pipeline"]
    labels   = list(pipeline.keys())
    values   = list(pipeline.values())
    colors   = ["#7C3AED","#A855F7","#6366F1","#10B981","#22C55E","#EF4444"]
    total    = sum(values) or 1

    col_chart, col_legend = st.columns([1, 1])
    with col_chart:
        fig = go.Figure(go.Pie(
            labels=labels, values=values,
            hole=0.62,
            marker=dict(colors=colors, line=dict(color="#0D0D14", width=2)),
            textinfo="none",
            hovertemplate="<b>%{label}</b><br>%{value} companies<br>%{percent}<extra></extra>",
        ))
        fig.add_annotation(text=f"<b>{stats['total_companies']}</b>", x=0.5, y=0.55,
                           font=dict(size=22, color="#EDE9FE"), showarrow=False)
        fig.add_annotation(text="Total Leads", x=0.5, y=0.42,
                           font=dict(size=11, color="#8B80C4"), showarrow=False)
        fig.update_layout(height=200, margin=dict(l=0,r=0,t=0,b=0), showlegend=False,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    with col_legend:
        st.markdown("<div style='padding-top:16px'>", unsafe_allow_html=True)
        for label, val, color in zip(labels, values, colors):
            pct = round(val/total*100,1)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;">
              <div style="width:10px;height:10px;border-radius:3px;background:{color};flex-shrink:0;"></div>
              <span style="color:#C4B5FD;font-size:0.8rem;flex:1;">{label}</span>
              <span style="color:#EDE9FE;font-size:0.8rem;font-weight:600;">{val:,}</span>
              <span style="color:#8B80C4;font-size:0.72rem;">({pct}%)</span>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown('<div style="font-weight:700;font-size:1rem;color:#DDD6FE;margin-bottom:12px;">Email Funnel</div>', unsafe_allow_html=True)
    sent      = stats["emails_sent"]
    delivered = stats.get("emails_delivered", sent)  # falls back to sent if bounce tracking not populated
    opened    = stats["emails_opened"]
    replied   = stats["emails_replied"]
    stages = [("Sent", sent, "#7C3AED"), ("Delivered", delivered, "#6366F1"),
              ("Opened", opened, "#38BDF8"), ("Replied", replied, "#10B981")]
    base = max(sent, 1)

    funnel_rows = "".join(
        f"""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
          <div style="width:78px;font-size:0.75rem;color:#C4B5FD;flex-shrink:0;">{s}</div>
          <div style="flex:1;background:#1E1B4B;border-radius:6px;overflow:hidden;height:26px;position:relative;">
            <div style="width:{max(v/base*100,3):.0f}%;height:100%;background:{c};
                        display:flex;align-items:center;justify-content:flex-end;padding-right:8px;">
              <span style="color:#fff;font-size:0.72rem;font-weight:700;">{v:,}</span>
            </div>
          </div>
          <div style="width:44px;text-align:right;font-size:0.72rem;color:#8B80C4;">
            {round(v/base*100)}%
          </div>
        </div>"""
        for s, v, c in stages
    )
    st.markdown(f'<div style="padding-top:6px">{funnel_rows}</div>', unsafe_allow_html=True)

st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)
st.divider()

# ── Recent Activities · My Tasks · AI Insights ────────────────────────────────
act_col, task_col, insight_col = st.columns(3)

with act_col:
    st.markdown('<div style="font-weight:700;font-size:1rem;color:#DDD6FE;margin-bottom:14px;">📋 Recent Activities</div>', unsafe_allow_html=True)
    activities = recent_activities(org_id, limit=6)
    if activities:
        for a in activities:
            st.markdown(f"""
            <div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;
                        border-bottom:1px solid #1E1B4B;">
              <div style="width:28px;height:28px;border-radius:8px;background:#1E1B4B;
                          display:flex;align-items:center;justify-content:center;
                          font-size:0.85rem;flex-shrink:0;">{a['icon']}</div>
              <div style="flex:1;min-width:0;">
                <div style="color:#C4B5FD;font-size:0.8rem;font-weight:500;
                            overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                  {a['title']}
                </div>
                <div style="color:#8B80C4;font-size:0.7rem;">{a['subtitle'] or ''}</div>
              </div>
              <div style="color:#7B6EA8;font-size:0.68rem;white-space:nowrap;">{humanize_delta(a['at'])}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#8B80C4;font-size:0.85rem;">No activity yet.</p>', unsafe_allow_html=True)

with task_col:
    st.markdown('<div style="font-weight:700;font-size:1rem;color:#DDD6FE;margin-bottom:14px;">✅ My Tasks</div>', unsafe_allow_html=True)
    open_tasks = task_svc.list_open(assigned_to_id=user.get("id"), limit=6) or task_svc.list_open(limit=6)
    prio_color = {"high": "#EF4444", "medium": "#F59E0B", "low": "#60A5FA"}
    if open_tasks:
        for t in open_tasks:
            c1, c2 = st.columns([0.15, 0.85])
            with c1:
                if st.checkbox("", key=f"task_done_{t['id']}", label_visibility="collapsed"):
                    task_svc.complete(t["id"])
                    st.rerun()
            with c2:
                pc = prio_color.get(t["priority"], "#8B80C4")
                due = f" · Due {t['due_date']}" if t["due_date"] else ""
                st.markdown(f"""
                <div style="padding:2px 0 10px;border-bottom:1px solid #1E1B4B;margin-bottom:2px;">
                  <div style="color:#DDD6FE;font-size:0.82rem;font-weight:500;">{t['title']}</div>
                  <div style="display:flex;align-items:center;gap:6px;margin-top:2px;">
                    <span style="background:{pc}22;color:{pc};border-radius:8px;padding:1px 8px;
                                font-size:0.65rem;font-weight:700;text-transform:uppercase;">{t['priority']}</span>
                    <span style="color:#7B6EA8;font-size:0.68rem;">{due}</span>
                  </div>
                </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#8B80C4;font-size:0.85rem;">Nothing on your plate — use <b>+ Add New</b> above to create one.</p>', unsafe_allow_html=True)

with insight_col:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;">
      <span style="font-weight:700;font-size:1rem;color:#DDD6FE;">🤖 AI Insights</span>
      <span style="background:rgba(124,58,237,0.2);color:#C4B5FD;border-radius:10px;
                   padding:1px 8px;font-size:0.65rem;font-weight:700;">BETA</span>
    </div>""", unsafe_allow_html=True)
    insights = compute_insights(org_id)
    if insights:
        for ins in insights:
            st.markdown(f"""
            <div style="background:#14112E;border:1px solid #2D2556;border-radius:12px;
                        padding:14px;margin-bottom:10px;">
              <div style="display:flex;align-items:center;gap:7px;margin-bottom:6px;">
                <span style="font-size:1rem;">{ins['icon']}</span>
                <span style="color:#DDD6FE;font-weight:600;font-size:0.82rem;">{ins['title']}</span>
              </div>
              <p style="color:#9580C4;font-size:0.75rem;line-height:1.4;margin:0;">{ins['body']}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"{ins['cta_label']} →", key=f"ins_cta_{ins['title']}", use_container_width=True):
                st.switch_page(ins["cta_page"])
    else:
        st.markdown("""
        <div style="background:#14112E;border:1px solid #2D2556;border-radius:12px;padding:16px;">
          <p style="color:#8B80C4;font-size:0.8rem;margin:0;line-height:1.5;">
            Not enough outreach history yet to surface a reliable insight —
            these are computed from real send/reply data, never guessed.
            Send a few more campaigns and check back here.
          </p>
        </div>""", unsafe_allow_html=True)

st.divider()

# ── Quick Actions ─────────────────────────────────────────────────────────────
st.markdown('<div style="font-weight:700;font-size:1rem;color:#DDD6FE;margin-bottom:14px;">⚡ Quick Actions</div>', unsafe_allow_html=True)
qa1, qa2, qa3, qa4, qa5 = st.columns(5)
with qa1:
    if st.button("🔍 Find Leads",     use_container_width=True, type="primary"): st.switch_page("pages/1_Companies.py")
with qa2:
    if st.button("🔄 BDM Workflow",   use_container_width=True): st.switch_page("pages/8_Workflow.py")
with qa3:
    if st.button("✉️ Outreach",       use_container_width=True): st.switch_page("pages/3_Outreach.py")
with qa4:
    if st.button("🔁 Follow-ups",     use_container_width=True): st.switch_page("pages/4_Followups.py")
with qa5:
    if st.button("💬 AI Chat",        use_container_width=True): st.switch_page("pages/6_AI_Chat.py")
