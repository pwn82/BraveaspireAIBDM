"""
Shared dashboard-style UI building blocks — used across every page so the
"redesigned dashboard" visual language (gradient KPI cards with inline
sparklines, consistent spacing/typography) stays consistent instead of each
page hand-rolling its own slightly-different version.
"""
from __future__ import annotations

import streamlit as st


def sparkline_svg(values: list, color: str, width: int = 100, height: int = 30) -> str:
    """Inline SVG polyline trend line — no chart library/iframe needed for a
    card-embedded sparkline. A flat baseline (not an empty/hidden element)
    when there's no data yet, so the card layout doesn't jump once data
    starts arriving."""
    if not values or max(values) == 0:
        points = f"0,{height - 2} {width},{height - 2}"
    else:
        vmax = max(values)
        n = len(values)
        step = width / max(1, n - 1)
        points = " ".join(
            f"{i * step:.1f},{height - 2 - (v / vmax) * (height - 4):.1f}"
            for i, v in enumerate(values)
        )
    return (
        f'<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" style="display:block;margin-top:6px">'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def kpi_card(col, label: str, value, delta: float = None, delta_label: str = "vs last 7 days",
            color: str = "#7C3AED", spark: list = None) -> None:
    """Render one gradient KPI card (optionally with a delta badge and an
    inline sparkline) into a Streamlit column."""
    delta_html = ""
    if delta is not None:
        sign  = "+" if delta >= 0 else ""
        dcolor = "#10B981" if delta >= 0 else "#EF4444"
        delta_html = (
            f'<div style="font-size:0.72rem;color:{dcolor};margin-top:4px;font-weight:500;">'
            f'{sign}{delta}% {delta_label}</div>'
        )
    spark_html = sparkline_svg(spark, color) if spark else ""
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
      {spark_html}
    </div>
    """, unsafe_allow_html=True)


def page_header(icon: str, title: str, subtitle: str) -> None:
    """Consistent page title + subtitle, matching the dashboard's header style."""
    st.markdown(f"""
    <div style="margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #1E1B4B;">
      <h1 style="margin:0;font-size:1.6rem;font-weight:800;color:#EDE9FE;">{icon} {title}</h1>
      <p style="margin:4px 0 0;color:#8B80C4;font-size:0.85rem;">{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)
