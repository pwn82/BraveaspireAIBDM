import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from app.database.db import init_db
from app.utils.helpers import load_settings, get_scoped_crm
from app.utils.ui_components import kpi_card, page_header

st.set_page_config(page_title="Analytics — BraveAspire", page_icon="📈", layout="wide")
_apply_theme()
init_db()
load_settings(st)

from app.utils.rbac import require_auth, require_permission
_current_user = require_auth()
require_permission("analytics.read", _current_user)

crm   = get_scoped_crm(st)
stats = crm.get_pipeline_stats()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.section-title{font-size:.95rem;font-weight:700;color:#E2E0F0;margin-bottom:.2rem}
.section-sub{font-size:.78rem;color:#9B8FD4;margin-bottom:.8rem}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
page_header("📈", "Analytics & Revenue", "Full-funnel performance · Pipeline health · Revenue tracking")

# ── KPI cards ─────────────────────────────────────────────────────────────────
open_rate  = stats["open_rate"]
reply_rate = stats["reply_rate"]
conv_rate  = stats["conversion_rate"]

from app.services.dashboard_service import kpi_sparklines
_spark = kpi_sparklines(crm.organization_id)

ka1, ka2, ka3, ka4, ka5, ka6 = st.columns(6)
kpi_card(ka1, "Companies",   f"{stats['total_companies']:,}", color="#7C3AED", spark=_spark["companies"])
kpi_card(ka2, "Contacts",    f"{stats['total_contacts']:,}", color="#A855F7", spark=_spark["verified_contacts"])
kpi_card(ka3, "Emails Sent", f"{stats['emails_sent']:,}", color="#6366F1", spark=_spark["emails_sent"])
kpi_card(ka4, "Open Rate",   f"{open_rate}%", color="#38BDF8" if open_rate >= 40 else "#F87171")
kpi_card(ka5, "Reply Rate",  f"{reply_rate}%", color="#10B981" if reply_rate >= 10 else "#F87171",
         spark=_spark["replies"])
kpi_card(ka6, "Win Rate",    f"{conv_rate}%", color="#34D399")
st.markdown("<div style='margin-bottom:20px'></div>", unsafe_allow_html=True)

# ── Row 1: Pipeline funnel + Donut ────────────────────────────────────────────
pipeline = stats["pipeline"]
stages   = list(pipeline.keys())
values   = list(pipeline.values())
COLORS   = ["#7C3AED", "#6D28D9", "#5B21B6", "#4C1D95", "#34D399", "#F87171"]

col_l, col_r = st.columns(2)

with col_l:
    st.markdown('<div class="section-title">🔽 Sales Pipeline Funnel</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Companies moving through each stage</div>', unsafe_allow_html=True)
    fig = go.Figure(go.Funnel(
        y=stages, x=values,
        textinfo="value+percent initial",
        marker=dict(color=COLORS[:len(stages)]),
        connector=dict(line=dict(color="#2D2556", width=1)),
    ))
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=5, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9B8FD4"),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    st.markdown('<div class="section-title">🍩 Pipeline Distribution</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Share of companies by stage</div>', unsafe_allow_html=True)
    total_v = sum(values) or 1
    fig2 = go.Figure(go.Pie(
        labels=stages, values=values,
        hole=0.55,
        marker=dict(colors=COLORS[:len(stages)], line=dict(color="#0D0D14", width=2)),
        textinfo="label+percent",
        textfont=dict(color="#E2E0F0", size=12),
    ))
    fig2.update_layout(
        height=320, margin=dict(l=0, r=20, t=5, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(font=dict(color="#9B8FD4"), bgcolor="rgba(0,0,0,0)"),
        annotations=[dict(text=f"<b>{sum(values)}</b><br>total",
                          x=0.5, y=0.5, font=dict(size=14, color="#E2E0F0"), showarrow=False)],
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Row 2: Email funnel + Industry ────────────────────────────────────────────
col_e, col_i = st.columns(2)

with col_e:
    st.markdown('<div class="section-title">📧 Email Performance</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Sent → Opened → Replied conversion</div>', unsafe_allow_html=True)
    email_stages = ["Sent", "Opened", "Replied"]
    email_values = [stats["emails_sent"], stats["emails_opened"], stats["emails_replied"]]
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(
        x=email_stages, y=email_values,
        marker=dict(color=["#7C3AED", "#A78BFA", "#34D399"],
                    line=dict(color="#0D0D14", width=1)),
        text=email_values, textposition="outside",
        textfont=dict(color="#E2E0F0"),
    ))
    fig3.update_layout(
        height=280, margin=dict(l=0, r=0, t=20, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=True, gridcolor="#2D2556", color="#9B8FD4"),
        xaxis=dict(showgrid=False, color="#9B8FD4"),
        font=dict(color="#9B8FD4"),
    )
    st.plotly_chart(fig3, use_container_width=True)

with col_i:
    st.markdown('<div class="section-title">🏭 Companies by Industry</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Lead distribution across verticals</div>', unsafe_allow_html=True)
    companies = crm.get_companies()
    if companies:
        df = pd.DataFrame(companies)
        if "industry" in df.columns and df["industry"].notna().any():
            ind_counts = df["industry"].value_counts().reset_index()
            ind_counts.columns = ["Industry", "Count"]
            ind_counts = ind_counts.head(8)
            fig4 = go.Figure(go.Bar(
                x=ind_counts["Count"], y=ind_counts["Industry"],
                orientation="h",
                marker=dict(color=ind_counts["Count"],
                            colorscale=[[0, "#4C1D95"], [1, "#7C3AED"]],
                            line=dict(color="#0D0D14", width=1)),
                text=ind_counts["Count"], textposition="outside",
                textfont=dict(color="#E2E0F0"),
            ))
            fig4.update_layout(
                height=280, margin=dict(l=0, r=20, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(showgrid=False, color="#9B8FD4", autorange="reversed"),
                xaxis=dict(showgrid=True, gridcolor="#2D2556", color="#9B8FD4"),
                font=dict(color="#9B8FD4"),
            )
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("No industry data yet.")
    else:
        st.info("No companies yet.")

st.divider()

# ── Row 3: Score histogram + Revenue ─────────────────────────────────────────
col_h, col_rev = st.columns(2)

with col_h:
    st.markdown('<div class="section-title">🎯 Lead Score Distribution</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">How AI-scored your leads</div>', unsafe_allow_html=True)
    if companies:
        df2 = pd.DataFrame(companies)
        if "score" in df2.columns and df2["score"].notna().any():
            fig5 = px.histogram(df2, x="score", nbins=10,
                                color_discrete_sequence=["#7C3AED"],
                                labels={"score": "Lead Score", "count": "Companies"})
            fig5.update_traces(marker_line_color="#0D0D14", marker_line_width=1)
            fig5.update_layout(
                height=240, margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(showgrid=True, gridcolor="#2D2556", color="#9B8FD4"),
                xaxis=dict(showgrid=False, color="#9B8FD4"),
                font=dict(color="#9B8FD4"), bargap=0.05,
            )
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.info("No scored leads yet.")
    else:
        st.info("No companies yet.")

with col_rev:
    st.markdown('<div class="section-title">💰 Revenue Tracker</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Estimated pipeline value vs annual goal</div>', unsafe_allow_html=True)

    won           = stats["pipeline"].get("Won", 0)
    revenue_est   = won * 15000
    target_annual = 120000
    progress      = min(revenue_est / target_annual * 100, 100) if target_annual else 0
    bar_pct       = min(int(progress), 100)

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Deals Won",    won)
        st.metric("Est. Revenue", f"${revenue_est:,}")
    with c2:
        st.metric("Annual Goal",  f"${target_annual:,}")
        st.metric("Progress",     f"{progress:.1f}%", delta=f"${revenue_est:,} earned")

    st.markdown(f"""
    <div style="margin-top:.6rem">
      <div style="display:flex;justify-content:space-between;font-size:.73rem;
        color:#9B8FD4;margin-bottom:.3rem">
        <span>$0</span>
        <span style="color:#C4B5FD">${revenue_est:,} earned</span>
        <span>${target_annual:,}</span>
      </div>
      <div style="background:#1A1830;border-radius:8px;height:10px;overflow:hidden">
        <div style="background:linear-gradient(90deg,#7C3AED,#A78BFA);
          width:{bar_pct}%;height:100%;border-radius:8px"></div>
      </div>
    </div>""", unsafe_allow_html=True)

st.divider()

# ── Goals / Success metrics ────────────────────────────────────────────────────
st.markdown('<div class="section-title">📋 Success Metrics vs Goals</div>', unsafe_allow_html=True)

goals_data = {
    "Metric":  ["Lead pipeline", "Email open rate", "Reply rate", "Deals closed", "Est. monthly revenue"],
    "Current": [
        f"{stats['total_companies']} companies",
        f"{open_rate}%",
        f"{reply_rate}%",
        f"{won} won",
        f"${revenue_est // 12:,}/mo",
    ],
    "Goal":    ["1,000+", "40%+", "10%+", "Active", "$10,000+/mo"],
    "Status":  [
        "✅ On Track" if stats["total_companies"] >= 1000 else "⚡ Building",
        "✅ On Track" if open_rate >= 40  else "⚡ Below",
        "✅ On Track" if reply_rate >= 10 else "⚡ Below",
        "✅ Active"   if won > 0          else "⚡ Building",
        "✅ On Track" if revenue_est // 12 >= 10000 else "⚡ Below",
    ],
}
st.dataframe(pd.DataFrame(goals_data), use_container_width=True, hide_index=True)
