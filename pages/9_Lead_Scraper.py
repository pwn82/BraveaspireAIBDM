import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
import pandas as pd
from app.database.db import init_db
from app.services.crm_service import CRMService
from app.agents.company_scraping_agent import CompanyScrapingAgent
from app.utils.rbac import require_auth, require_permission
from app.utils.helpers import load_settings, get_ai_service

st.set_page_config(page_title="Lead Scraper — BraveAspire", page_icon="🔎", layout="wide")
_apply_theme()
init_db()
load_settings(st)

current_user = require_auth()
require_permission("scraping.run", current_user)

crm = CRMService()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.pg-title{font-size:1.75rem;font-weight:700;color:#F0EEFF;margin:0}
.pg-sub{font-size:.85rem;color:#9B8FD4;margin:.2rem 0 1.4rem 0;
  padding-bottom:1rem;border-bottom:1px solid #2D2556}
.source-badge{display:inline-block;background:#2D2556;border-radius:4px;
  padding:2px 8px;font-size:.72rem;color:#C4B5FD;margin:.1rem}
.result-card{background:#1A1830;border:1px solid #2D2556;border-radius:10px;
  padding:1rem;margin-bottom:.6rem}
.score-hi{color:#34D399;font-weight:700}
.score-mid{color:#F59E0B;font-weight:700}
.score-lo{color:#F87171;font-weight:700}
.api-status{display:inline-block;border-radius:6px;padding:3px 10px;
  font-size:.75rem;font-weight:600}
.api-ok{background:#064E3B;color:#34D399}
.api-no{background:#2A1A0A;color:#F87171}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="pg-title">🔎 Lead Scraper</div>', unsafe_allow_html=True)
st.markdown('<div class="pg-sub">Module 1 — Multi-source company discovery · AI scoring · Hiring & funding detection</div>',
            unsafe_allow_html=True)

# ── Resolve API keys: session_state (set via Settings) → env fallback ─────────
def _has_key(ss_key: str, env_key: str) -> bool:
    return bool(st.session_state.get(ss_key) or os.getenv(env_key))

def _get_key(ss_key: str, env_key: str) -> str:
    return st.session_state.get(ss_key) or os.getenv(env_key, "")

# ── API status badges ─────────────────────────────────────────────────────────
api_keys = {
    "Apollo.io":    _has_key("apollo_api_key",      "APOLLO_API_KEY"),
    "Google Maps":  _has_key("google_maps_api_key", "GOOGLE_MAPS_API_KEY"),
    "Crunchbase":   _has_key("crunchbase_api_key",  "CRUNCHBASE_API_KEY"),
    "Proxycurl":    _has_key("proxycurl_api_key",   "PROXYCURL_API_KEY"),
    "Apify":        _has_key("apify_api_token",     "APIFY_API_TOKEN"),
    "Clutch.co":    True,   # web scraping — no key needed
    "Indeed":       True,
    "Naukri":       True,
}

badge_html = ""
for name, ok in api_keys.items():
    css   = "api-ok" if ok else "api-no"
    icon  = "✅" if ok else "⚙️"
    badge_html += f'<span class="api-status {css}">{icon} {name}</span> '
st.markdown(f'<div style="margin-bottom:1rem">{badge_html}</div>', unsafe_allow_html=True)

if not any(v for k, v in api_keys.items() if k not in ("Clutch.co", "Indeed", "Naukri")):
    st.info("💡 No paid API keys configured. Go to **Settings → 🔑 API Keys** to add "
            "**Apollo.io**, **Google Maps**, **Crunchbase**, or **Apify** keys for richer results. "
            "Clutch.co, Indeed, and Naukri scraping work without any keys.")

st.divider()

# ── Search configuration ──────────────────────────────────────────────────────
st.subheader("1. Define Your Search")

col_q, col_n = st.columns([5, 1])
with col_q:
    query = st.text_input(
        "What type of companies are you looking for?",
        placeholder="SaaS startups hiring Python engineers, fintech companies with outdated systems...",
        key="scraper_query",
    )
with col_n:
    count = st.number_input("Max results", min_value=5, max_value=50, value=15, key="scraper_count")

col_1, col_2, col_3 = st.columns(3)
with col_1:
    f_industry  = st.text_input("Industry",       placeholder="Fintech, Healthcare, SaaS...", key="f_ind")
    f_location  = st.text_input("Location",       placeholder="Mumbai, USA, London...",       key="f_loc")
with col_2:
    f_emp_size  = st.text_input("Employee size",  placeholder="50-200, 100-500...",           key="f_emp")
    f_technology= st.text_input("Technology",     placeholder="React, Python, Node.js...",    key="f_tech")
with col_3:
    f_hiring    = st.checkbox("🟢 Actively hiring only",    value=False, key="f_hiring")
    f_funding   = st.checkbox("💰 Has funding / investor-backed", value=False, key="f_fund")
    f_outdated  = st.checkbox("🔴 Outdated tech (opportunity)", value=False, key="f_outdated")

st.markdown("**Data sources to use:**")
# Ordered (API key required → free)
src_map = {
    "apollo":      ("Apollo.io",    _has_key("apollo_api_key",      "APOLLO_API_KEY"),   "🔑"),
    "google_maps": ("Google Maps",  _has_key("google_maps_api_key", "GOOGLE_MAPS_API_KEY"), "🔑"),
    "crunchbase":  ("Crunchbase",   _has_key("crunchbase_api_key",  "CRUNCHBASE_API_KEY"), "🔑"),
    "apify":       ("Apify",        _has_key("apify_api_token",     "APIFY_API_TOKEN"),  "🔑"),
    "clutch":      ("Clutch.co",    True,  "🆓"),
    "indeed":      ("Indeed",       True,  "🆓"),
    "naukri":      ("Naukri",       True,  "🆓"),
}
src_cols = st.columns(len(src_map))
selected_sources = []
for i, (key, (label, has_key, badge)) in enumerate(src_map.items()):
    with src_cols[i]:
        icon  = "✅" if has_key else "⚙️"
        tip   = None if has_key else "Add key in Settings → 🔑 API Keys"
        if st.checkbox(f"{badge} {label}", value=has_key, key=f"src_{key}", help=tip):
            selected_sources.append(key)

st.divider()

# ── Run ───────────────────────────────────────────────────────────────────────
st.subheader("2. Run Discovery")

# Build effective search string from any filled field (query OR industry OR location)
_effective_query = " ".join(filter(None, [query.strip(), f_industry.strip(), f_location.strip()]))

# Show preview of what will be searched + which sources are active
if _effective_query and selected_sources:
    st.info(
        f"🎯 Will search **{len(selected_sources)} source(s)** "
        f"({', '.join(selected_sources)}) for: **{_effective_query}**"
    )
elif not _effective_query:
    st.caption("💡 Enter at least one of: search query, industry, or location below.")
elif not selected_sources:
    st.caption("💡 Select at least one data source above.")

run_col, _ = st.columns([2, 5])
with run_col:
    run_btn = st.button(
        "🚀 Start Scraping",
        type="primary",
        disabled=False,                  # always clickable — we validate inside
        use_container_width=True,
        key="scrape_run_btn",
    )

# ── Pre-flight validation feedback ────────────────────────────────────────────
if run_btn:
    if not _effective_query:
        st.error("⚠️ Please enter at least one of: **search query**, **industry**, or **location** above.")
    elif not selected_sources:
        st.error("⚠️ Please select at least one data source above.")

if "scraper_results" not in st.session_state:
    st.session_state.scraper_results = []
if "scraper_src_errors" not in st.session_state:
    st.session_state.scraper_src_errors = []

if run_btn and _effective_query and selected_sources:
    # Use the effective query (may be just industry+location if query box was empty)
    query = _effective_query
    ai_svc = get_ai_service(st)

    # Pass all API keys resolved from session_state (set via Settings → 🔑 API Keys)
    _runtime_keys = {
        "apollo_api_key":      _get_key("apollo_api_key",      "APOLLO_API_KEY"),
        "google_maps_api_key": _get_key("google_maps_api_key", "GOOGLE_MAPS_API_KEY"),
        "crunchbase_api_key":  _get_key("crunchbase_api_key",  "CRUNCHBASE_API_KEY"),
        "proxycurl_api_key":   _get_key("proxycurl_api_key",   "PROXYCURL_API_KEY"),
        "apify_api_token":     _get_key("apify_api_token",     "APIFY_API_TOKEN"),
        "hunter_api_key":      _get_key("hunter_api_key",      "HUNTER_API_KEY"),
    }
    agent = CompanyScrapingAgent(ai_service=ai_svc, api_keys=_runtime_keys)

    with st.spinner(f"🔍 Searching {len(selected_sources)} sources for **{query}**..."):
        results = agent.search(
            query=query,
            industry=f_industry,
            location=f_location,
            employee_size=f_emp_size,
            technology=f_technology,
            hiring=f_hiring,
            count=int(count),
            sources=selected_sources if selected_sources else None,
        )

    # ── Surface per-source errors to the user ────────────────────────────
    if agent.errors:
        for _err in agent.errors:
            if "TIMED-OUT" in _err or "timed-out" in _err.lower():
                st.warning(
                    f"⚠️ Apify rate limit hit — the Google Maps scraper allows **~1 search "
                    f"per 30 minutes** on the free plan. Wait a few minutes and try again, "
                    f"or upgrade your Apify plan at [apify.com/pricing](https://apify.com/pricing) "
                    f"for unlimited runs."
                )
            else:
                st.warning(f"⚠️ Source error — {_err}")

    # Apply additional filters
    if f_funding:
        results = [r for r in results if r.get("funding_stage") or r.get("funding_amount")]
    if f_outdated:
        results = [r for r in results if "outdated" in (r.get("pain_points") or "").lower()]

    st.session_state.scraper_results   = results
    st.session_state.scraper_src_errors = agent.errors[:]
    st.success(f"✅ Found **{len(results)}** companies matching your criteria.")
    st.rerun()

# ── Results display ───────────────────────────────────────────────────────────
results = st.session_state.scraper_results

# ── Show any stored source errors from the last run ───────────────────────────
for _e in st.session_state.get("scraper_src_errors", []):
    st.warning(f"⚠️ Source error — {_e}")

if results:
    # Detect if ALL results are demo (no real API data came back)
    _all_demo = all(r.get("source", "").startswith("Demo") for r in results)
    if _all_demo:
        st.error(
            "🔴 **Showing demo/placeholder data** — no live sources returned results.\n\n"
            "To get real company data:\n"
            "- Go to **Settings → 🔑 API Keys** and add your **Apify** token *(recommended — "
            "covers Google Maps, LinkedIn, Indeed)*\n"
            "- Or add **Apollo.io**, **Google Maps**, or **Crunchbase** keys individually\n\n"
            "Clutch.co / Indeed scrapers work without keys but may be blocked by the "
            "target site's bot protection."
        )

    st.subheader(f"3. Results — {len(results)} Companies")

    # Summary chips
    hiring_cnt  = sum(1 for r in results if r.get("hiring_status"))
    funding_cnt = sum(1 for r in results if r.get("funding_stage"))
    outdated_cnt= sum(1 for r in results if "outdated" in (r.get("pain_points") or "").lower())

    st.markdown(
        f"**{hiring_cnt}** actively hiring &nbsp;·&nbsp; "
        f"**{funding_cnt}** with funding &nbsp;·&nbsp; "
        f"**{outdated_cnt}** outdated tech detected"
    )

    # Table view
    rows = []
    for r in results:
        score = r.get("score", 0)
        score_str = (f"🟢 {score}" if score >= 80
                     else f"🟡 {score}" if score >= 60 else f"🔴 {score}")
        rows.append({
            "Company":     r.get("name", ""),
            "Industry":    r.get("industry", ""),
            "Location":    r.get("location", ""),
            "Employees":   r.get("employee_size", 0) or "—",
            "Score":       score_str,
            "Hiring":      "✅ Yes" if r.get("hiring_status") else "—",
            "Funding":     r.get("funding_stage") or "—",
            "Tech":        (r.get("tech_stack") or "—")[:40],
            "Source":      r.get("source", ""),
        })

    selected_indices = []
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Detailed cards + selection ────────────────────────────────────────────
    st.markdown("**Select companies to import into CRM:**")

    selected_to_import = []
    for i, r in enumerate(results):
        score = r.get("score", 0)
        score_class = "score-hi" if score >= 80 else ("score-mid" if score >= 60 else "score-lo")

        col_chk, col_info = st.columns([1, 10])
        with col_chk:
            # Auto-select all results with score ≥ 50 (Apify scores hover ~53)
            if st.checkbox("", key=f"sel_co_{i}", value=score >= 50,
                           label_visibility="collapsed"):
                selected_to_import.append(r)
        with col_info:
            with st.expander(
                f"**{r.get('name')}** — {r.get('industry','?')} | "
                f"Score: {score} | {r.get('location','')}",
                expanded=False,
            ):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown(f"**Website:** {r.get('website') or '—'}")
                    st.markdown(f"**Employees:** {r.get('employee_size') or '—'}")
                    st.markdown(f"**Revenue:** {r.get('revenue') or '—'}")
                with col_b:
                    st.markdown(f"**Hiring:** {'✅ Yes' if r.get('hiring_status') else '❌ No'}")
                    st.markdown(f"**Job Openings:** {r.get('job_openings') or '—'}")
                    st.markdown(f"**Tech Stack:** {r.get('tech_stack') or '—'}")
                with col_c:
                    st.markdown(f"**Funding Stage:** {r.get('funding_stage') or '—'}")
                    st.markdown(f"**Funding Amount:** {r.get('funding_amount') or '—'}")
                    st.markdown(f"**Source:** {r.get('source','')}")
                if r.get("pain_points"):
                    st.markdown(f"**Pain Points / Notes:** {r['pain_points']}")
                if r.get("linkedin_url"):
                    st.markdown(f"[🔗 LinkedIn]({r['linkedin_url']})")

    # ── Import button ─────────────────────────────────────────────────────────
    st.divider()
    import_col, export_col = st.columns([2, 2])

    with import_col:
        if st.button(
            f"💾 Import {len(selected_to_import)} Selected to CRM",
            type="primary",
            disabled=not selected_to_import,
            key="import_to_crm_btn",
        ):
            imported = 0
            skipped  = 0
            for co in selected_to_import:
                # Check if already in CRM
                existing = crm.get_companies(search=co.get("name", ""))
                exact_match = any(
                    e.get("name","").lower() == co.get("name","").lower()
                    for e in existing
                )
                if exact_match:
                    skipped += 1
                    continue

                crm.add_company({
                    "name":          co.get("name", ""),
                    "website":       co.get("website", ""),
                    "industry":      co.get("industry", ""),
                    "location":      co.get("location", ""),
                    "employee_size": co.get("employee_size") or 0,
                    "revenue":       co.get("revenue", ""),
                    "score":         co.get("score", 0),
                    "status":        "New",
                    "hiring_status": co.get("hiring_status", False),
                    "tech_stack":    co.get("tech_stack", ""),
                    "pain_points":   co.get("pain_points", ""),
                    "notes":         co.get("notes", ""),
                    "source":        co.get("source", "Scraper"),
                    "linkedin_url":  co.get("linkedin_url", ""),
                    "funding_stage": co.get("funding_stage", ""),
                    "funding_amount":co.get("funding_amount",""),
                    "job_openings":  co.get("job_openings", 0),
                })
                imported += 1

            st.success(f"✅ Imported **{imported}** companies. "
                       + (f"⚠️ Skipped {skipped} duplicates." if skipped else ""))
            st.session_state.scraper_results = []
            st.rerun()

    with export_col:
        df_export = pd.DataFrame(results)
        csv = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export All to CSV",
            data=csv,
            file_name=f"leads_{query[:20].replace(' ','_')}.csv",
            mime="text/csv",
            key="export_csv_btn",
        )

elif not run_btn:
    st.markdown("""
    <div style="text-align:center;padding:3rem;color:#6B7280;
      background:#12102A;border:1px solid #2D2556;border-radius:12px">
      <div style="font-size:2.5rem;margin-bottom:.5rem">🔎</div>
      <div style="font-size:1rem;font-weight:600;color:#E2E0F0;margin-bottom:.3rem">
        Ready to discover leads
      </div>
      <div>Configure your search criteria above and click <strong>Start Scraping</strong></div>
    </div>""", unsafe_allow_html=True)
