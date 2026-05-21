import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from app.database.db import init_db, seed_demo_data
from app.services.crm_service import CRMService
from app.utils.helpers import load_settings, status_emoji
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

    from app.utils.rbac import ROLE_DISPLAY, has_permission
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
            seed_demo_data(); st.success("Demo data loaded!"); st.rerun()
        if st.button("Logout", use_container_width=True):
            for k in ["authenticated","user","token"]: st.session_state.pop(k, None)
            st.rerun()

# ── Dashboard ─────────────────────────────────────────────────────────────────
crm   = CRMService()
stats = crm.get_pipeline_stats()
hour  = datetime.now().hour
greet = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
name  = user.get("full_name", user.get("email","").split("@")[0]).title()

# Header
st.markdown(f"""
<div style="display:flex;align-items:flex-start;justify-content:space-between;
            margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid #1E1B4B;">
  <div>
    <h1 style="margin:0;font-size:1.75rem;font-weight:800;color:#EDE9FE;">
      {greet}, {name} 👋
    </h1>
    <p style="margin:4px 0 0;color:#8B80C4;font-size:0.875rem;">
      Here's what's happening with your pipeline today.
    </p>
  </div>
  <div style="color:#8B80C4;font-size:0.82rem;padding-top:6px;">
    {datetime.now().strftime('%B %d, %Y')}
  </div>
</div>
""", unsafe_allow_html=True)

# ── KPI Cards ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
active = stats["pipeline"].get("Interested",0) + stats["pipeline"].get("Proposal",0)

def kpi_card(col, label, value, delta=None, delta_label="vs last 7 days", icon="📊", color="#7C3AED"):
    delta_html = ""
    if delta is not None:
        sign  = "+" if delta >= 0 else ""
        dcolor = "#10B981" if delta >= 0 else "#EF4444"
        delta_html = f'<div style="font-size:0.72rem;color:{dcolor};margin-top:4px;font-weight:500;">{sign}{delta}% {delta_label}</div>'
    col.markdown(f"""
    <div style="background:linear-gradient(135deg,#16133A,#12102A);border:1px solid #2D2556;
                border-radius:14px;padding:18px 20px;position:relative;overflow:hidden;
                transition:all 0.25s;">
      <div style="position:absolute;top:0;left:0;right:0;height:2px;
                  background:linear-gradient(90deg,{color},{color}80);"></div>
      <div style="font-size:0.7rem;color:#9580C4;font-weight:700;text-transform:uppercase;
                  letter-spacing:0.08em;margin-bottom:8px;">{label}</div>
      <div style="font-size:1.9rem;font-weight:800;color:#EDE9FE;letter-spacing:-0.02em;
                  line-height:1;">{value}</div>
      {delta_html}
    </div>
    """, unsafe_allow_html=True)

with k1: kpi_card(k1, "Total Companies", f"{stats['total_companies']:,}", 11.3, icon="🏢")
with k2: kpi_card(k2, "Verified Contacts", f"{stats['total_contacts']:,}", 8.2, icon="👤", color="#A855F7")
with k3: kpi_card(k3, "Emails Sent", f"{stats['emails_sent']:,}", 15.3, icon="✉️", color="#6366F1")
with k4: kpi_card(k4, "Reply Rate", f"{stats['reply_rate']}%", round(stats['reply_rate']-5,1), icon="💬", color="#8B5CF6")
with k5: kpi_card(k5, "Active Leads", f"{active:,}", 3.2, delta_label="vs last week", icon="🎯", color="#7C3AED")

st.markdown("<div style='margin-bottom:24px'></div>", unsafe_allow_html=True)

# ── Pipeline Overview + Reply Rate ────────────────────────────────────────────
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
    fig2 = go.Figure()
    stages = ["Sent", "Opened", "Replied"]
    vals   = [stats["emails_sent"], stats["emails_opened"], stats["emails_replied"]]
    s_colors = ["#7C3AED","#A855F7","#10B981"]
    for i, (s, v, c) in enumerate(zip(stages, vals, s_colors)):
        pct = round(v / max(vals[0],1) * 100, 0)
        fig2.add_trace(go.Bar(name=s, x=[v], y=[s], orientation='h',
                              marker=dict(color=c, line=dict(width=0)),
                              text=f"{v:,} ({pct:.0f}%)", textposition="auto",
                              textfont=dict(color="#fff", size=11)))
    fig2.update_layout(height=200, barmode="overlay", showlegend=False,
                       margin=dict(l=0,r=0,t=0,b=0),
                       paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                       xaxis=dict(showgrid=False, showticklabels=False, color="#8B80C4"),
                       yaxis=dict(color="#C4B5FD", tickfont=dict(size=12)))
    st.plotly_chart(fig2, use_container_width=True)

st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)
st.divider()

# ── AI Insights + Activity Feed ───────────────────────────────────────────────
ins_col, feed_col = st.columns([3, 2])

with ins_col:
    st.markdown('<div style="font-weight:700;font-size:1rem;color:#DDD6FE;margin-bottom:14px;">🤖 AI Insights</div>', unsafe_allow_html=True)
    insights = [
        ("🔥", "Hot Leads",           "#EF4444",
         f"{stats['pipeline'].get('Interested',0)} companies are actively hiring for roles matching your ideal customer profile.",
         "View Leads →"),
        ("📧", "Best Performing",     "#10B981",
         f"Your outreach has {stats['open_rate']}% open rate. Reply rate is {stats['reply_rate']}% this week.",
         "View Templates →"),
        ("⚠️", "Action Needed",       "#F59E0B",
         f"{stats['pipeline'].get('Proposal',0)} follow-ups are pending. Take action to increase reply rate.",
         "View Follow-ups →"),
    ]
    cols = st.columns(3)
    for col, (icon, title, color, desc, cta) in zip(cols, insights):
        col.markdown(f"""
        <div style="background:#14112E;border:1px solid #2D2556;border-radius:12px;
                    padding:14px;height:140px;border-top:2px solid {color};">
          <div style="display:flex;align-items:center;gap:7px;margin-bottom:8px;">
            <span style="font-size:1rem;">{icon}</span>
            <span style="color:#DDD6FE;font-weight:600;font-size:0.82rem;">{title}</span>
          </div>
          <p style="color:#9580C4;font-size:0.75rem;line-height:1.4;margin:0 0 8px;">{desc}</p>
          <span style="color:{color};font-size:0.72rem;font-weight:600;cursor:pointer;">{cta}</span>
        </div>
        """, unsafe_allow_html=True)

with feed_col:
    st.markdown('<div style="font-weight:700;font-size:1rem;color:#DDD6FE;margin-bottom:14px;">📋 Activity Feed</div>', unsafe_allow_html=True)
    outreach = crm.get_outreach()[:5]
    if outreach:
        for o in outreach:
            status  = o.get("status","")
            contact = o.get("contact_name","Unknown")
            company = o.get("company_name","—")
            date    = (o.get("sent_at") or o.get("created_at",""))[:10]
            s_color = {"Sent":"#7C3AED","Opened":"#10B981","Replied":"#A855F7",
                       "Draft":"#8B80C4","Bounced":"#EF4444"}.get(status,"#8B80C4")
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;padding:8px 0;
                        border-bottom:1px solid #1E1B4B;">
              <div style="width:7px;height:7px;border-radius:50%;background:{s_color};flex-shrink:0;"></div>
              <div style="flex:1;min-width:0;">
                <div style="color:#C4B5FD;font-size:0.8rem;font-weight:500;
                            overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                  {contact} @ {company}
                </div>
                <div style="color:#8B80C4;font-size:0.7rem;">{status} · {date}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#8B80C4;font-size:0.85rem;">No activity yet.</p>', unsafe_allow_html=True)

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

# ── Bottom stats ──────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div style="font-weight:700;font-size:1rem;color:#DDD6FE;margin-bottom:14px;">📊 Performance Summary</div>', unsafe_allow_html=True)
m1, m2, m3, m4, m5 = st.columns(5)
with m1: st.metric("Contacts",       stats["total_contacts"])
with m2: st.metric("Deals Won",      stats["pipeline"].get("Won",0))
with m3: st.metric("Win Rate",       f"{stats['conversion_rate']}%")
with m4: st.metric("Total Outreach", stats["total_outreach"])
with m5:
    from app.services.email_tracking_service import get_tracking_stats
    st.metric("Tracked Opens", get_tracking_stats()["unique_opens"])
