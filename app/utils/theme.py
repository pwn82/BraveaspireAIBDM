"""
BraveAspire — Deep Indigo Professional Dark Theme
Inject into any Streamlit page:
    from app.utils.theme import apply_theme
    apply_theme()
"""
import streamlit as st


def apply_theme():
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = """
<style>
/* ── Google Fonts: Inter ─────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* ── Main background ─────────────────────────────────────────────────────── */
.stApp {
    background: #0D0D14;
}

/* ════════════════════════════════════════════════════════════════════════════
   SIDEBAR  — Deep Indigo
   ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #12102A 0%, #0E0C22 100%) !important;
    border-right: 1px solid #2D2556 !important;
    box-shadow: 4px 0 24px rgba(124,58,237,0.08) !important;
}

/* All text in sidebar */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div {
    color: #C4B5FD !important;
}

/* Nav links */
[data-testid="stSidebarNav"] a {
    border-radius: 8px !important;
    margin: 2px 10px !important;
    padding: 7px 14px !important;
    color: #A78BFA !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    transition: all 0.18s ease !important;
    border: 1px solid transparent !important;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(124,58,237,0.12) !important;
    border-color: rgba(124,58,237,0.25) !important;
    color: #C4B5FD !important;
    transform: translateX(2px) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: rgba(124,58,237,0.2) !important;
    border-color: rgba(124,58,237,0.5) !important;
    color: #DDD6FE !important;
    font-weight: 600 !important;
    box-shadow: 0 0 12px rgba(124,58,237,0.2) !important;
}

/* Sidebar page_link items */
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
    border-radius: 8px !important;
    margin: 2px 4px !important;
    padding: 7px 12px !important;
    color: #A78BFA !important;
    font-weight: 500 !important;
    transition: all 0.18s ease !important;
    border: 1px solid transparent !important;
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {
    background: rgba(124,58,237,0.12) !important;
    border-color: rgba(124,58,237,0.25) !important;
    color: #C4B5FD !important;
    transform: translateX(3px) !important;
}
[data-testid="stSidebar"] [data-testid="stPageLink-active"] a {
    background: rgba(124,58,237,0.2) !important;
    border-color: rgba(124,58,237,0.45) !important;
    color: #DDD6FE !important;
    font-weight: 600 !important;
}

/* Sidebar divider */
[data-testid="stSidebar"] hr {
    border-color: #2D2556 !important;
}

/* Sidebar buttons */
[data-testid="stSidebar"] button {
    background: rgba(124,58,237,0.12) !important;
    border: 1px solid #3D3080 !important;
    color: #C4B5FD !important;
    border-radius: 8px !important;
    transition: all 0.2s !important;
}
[data-testid="stSidebar"] button:hover {
    background: rgba(124,58,237,0.25) !important;
    border-color: #7C3AED !important;
}

/* Sidebar expander */
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(124,58,237,0.07) !important;
    border: 1px solid #2D2556 !important;
    border-radius: 10px !important;
}

/* ════════════════════════════════════════════════════════════════════════════
   METRIC CARDS
   ════════════════════════════════════════════════════════════════════════════ */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #16133A 0%, #12102A 100%) !important;
    border: 1px solid #2D2556 !important;
    border-radius: 14px !important;
    padding: 18px 22px !important;
    transition: all 0.25s ease !important;
    position: relative !important;
    overflow: hidden !important;
}
[data-testid="metric-container"]::before {
    content: '' !important;
    position: absolute !important;
    top: 0 !important; left: 0 !important;
    right: 0 !important; height: 2px !important;
    background: linear-gradient(90deg, #7C3AED, #A855F7, #C084FC) !important;
    border-radius: 14px 14px 0 0 !important;
}
[data-testid="metric-container"]:hover {
    border-color: #7C3AED !important;
    box-shadow: 0 4px 20px rgba(124,58,237,0.25) !important;
    transform: translateY(-2px) !important;
}
[data-testid="stMetricLabel"] {
    color: #9580C4 !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}
[data-testid="stMetricValue"] {
    color: #EDE9FE !important;
    font-size: 1.85rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em !important;
}
[data-testid="stMetricDelta"] svg { display: none !important; }

/* ════════════════════════════════════════════════════════════════════════════
   BUTTONS
   ════════════════════════════════════════════════════════════════════════════ */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7C3AED 0%, #5B21B6 100%) !important;
    border: none !important;
    border-radius: 9px !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    letter-spacing: 0.02em !important;
    padding: 9px 22px !important;
    box-shadow: 0 2px 12px rgba(124,58,237,0.4) !important;
    transition: all 0.22s ease !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #8B5CF6 0%, #6D28D9 100%) !important;
    box-shadow: 0 6px 20px rgba(124,58,237,0.55) !important;
    transform: translateY(-2px) !important;
}
.stButton > button[kind="primary"]:active {
    transform: translateY(0) !important;
    box-shadow: 0 2px 8px rgba(124,58,237,0.4) !important;
}
.stButton > button:not([kind="primary"]) {
    background: #1A1730 !important;
    border: 1px solid #2D2556 !important;
    border-radius: 9px !important;
    color: #C4B5FD !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}
.stButton > button:not([kind="primary"]):hover {
    background: #231F40 !important;
    border-color: #7C3AED !important;
    color: #DDD6FE !important;
    box-shadow: 0 0 12px rgba(124,58,237,0.15) !important;
}

/* ════════════════════════════════════════════════════════════════════════════
   INPUTS
   ════════════════════════════════════════════════════════════════════════════ */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div,
.stNumberInput > div > div > input,
.stMultiSelect > div > div > div {
    background: #16133A !important;
    border: 1px solid #2D2556 !important;
    border-radius: 9px !important;
    color: #E2E0F0 !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #7C3AED !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.2) !important;
    outline: none !important;
}
.stTextInput label, .stTextArea label,
.stSelectbox label, .stNumberInput label {
    color: #A78BFA !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
}

/* ════════════════════════════════════════════════════════════════════════════
   TABS
   ════════════════════════════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {
    background: #12102A !important;
    border-radius: 12px !important;
    padding: 5px !important;
    gap: 4px !important;
    border: 1px solid #2D2556 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 8px !important;
    color: #8B80C4 !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    padding: 7px 18px !important;
    transition: all 0.2s ease !important;
    border: none !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #7C3AED, #5B21B6) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 10px rgba(124,58,237,0.45) !important;
}
.stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]) {
    background: rgba(124,58,237,0.1) !important;
    color: #C4B5FD !important;
}

/* ════════════════════════════════════════════════════════════════════════════
   DATAFRAMES
   ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stDataFrame"] {
    border: 1px solid #2D2556 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.3) !important;
}
[data-testid="stDataFrame"] thead tr th {
    background: #16133A !important;
    color: #9580C4 !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    border-bottom: 1px solid #2D2556 !important;
    padding: 10px 14px !important;
}
[data-testid="stDataFrame"] tbody tr:hover td {
    background: rgba(124,58,237,0.08) !important;
}
[data-testid="stDataFrame"] tbody tr td {
    border-color: #1E1B4B !important;
    color: #C4B5FD !important;
}

/* ════════════════════════════════════════════════════════════════════════════
   EXPANDERS
   ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stExpander"] {
    background: #14112E !important;
    border: 1px solid #2D2556 !important;
    border-radius: 12px !important;
    margin-bottom: 8px !important;
    transition: border-color 0.2s !important;
}
[data-testid="stExpander"]:hover {
    border-color: #7C3AED !important;
}
[data-testid="stExpander"] summary {
    color: #C4B5FD !important;
    font-weight: 500 !important;
    padding: 12px 16px !important;
}
[data-testid="stExpander"] summary:hover {
    color: #DDD6FE !important;
}
[data-testid="stExpander"] svg {
    color: #7C3AED !important;
    fill: #7C3AED !important;
}

/* ════════════════════════════════════════════════════════════════════════════
   ALERTS
   ════════════════════════════════════════════════════════════════════════════ */
.stSuccess {
    background: rgba(16,185,129,0.08) !important;
    border: 1px solid rgba(16,185,129,0.3) !important;
    border-left: 4px solid #10B981 !important;
    border-radius: 0 10px 10px 0 !important;
    color: #6EE7B7 !important;
}
.stWarning {
    background: rgba(245,158,11,0.08) !important;
    border: 1px solid rgba(245,158,11,0.3) !important;
    border-left: 4px solid #F59E0B !important;
    border-radius: 0 10px 10px 0 !important;
    color: #FCD34D !important;
}
.stError {
    background: rgba(239,68,68,0.08) !important;
    border: 1px solid rgba(239,68,68,0.3) !important;
    border-left: 4px solid #EF4444 !important;
    border-radius: 0 10px 10px 0 !important;
    color: #FCA5A5 !important;
}
.stInfo {
    background: rgba(124,58,237,0.08) !important;
    border: 1px solid rgba(124,58,237,0.3) !important;
    border-left: 4px solid #7C3AED !important;
    border-radius: 0 10px 10px 0 !important;
    color: #C4B5FD !important;
}

/* ════════════════════════════════════════════════════════════════════════════
   MISC
   ════════════════════════════════════════════════════════════════════════════ */
hr {
    border: none !important;
    border-top: 1px solid #1E1B4B !important;
    margin: 24px 0 !important;
}

code, pre {
    background: #16133A !important;
    border: 1px solid #2D2556 !important;
    border-radius: 6px !important;
    color: #C4B5FD !important;
}

.stProgress > div > div > div {
    background: linear-gradient(90deg, #7C3AED, #A855F7, #C084FC) !important;
    border-radius: 4px !important;
}

h1 {
    color: #EDE9FE !important;
    font-weight: 800 !important;
    letter-spacing: -0.03em !important;
}
h2 { color: #DDD6FE !important; font-weight: 700 !important; }
h3 { color: #C4B5FD !important; font-weight: 600 !important; }

p, li { color: #C4B5FD !important; }

/* Caption / small text */
[data-testid="stCaptionContainer"], small, .caption {
    color: #8B80C4 !important;
}

/* Checkbox */
[data-testid="stCheckbox"] span { color: #C4B5FD !important; }

/* Radio buttons */
[data-testid="stRadio"] span { color: #C4B5FD !important; }
[data-testid="stRadio"] label { color: #C4B5FD !important; }

/* Spinner */
.stSpinner > div {
    border-color: #7C3AED transparent transparent transparent !important;
}

/* Top header bar */
[data-testid="stHeader"] {
    background: rgba(13,13,20,0.92) !important;
    border-bottom: 1px solid #1E1B4B !important;
    backdrop-filter: blur(12px) !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #0D0D14; }
::-webkit-scrollbar-thumb { background: #2D2556; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #7C3AED; }

/* Form submit button */
[data-testid="stFormSubmitButton"] button {
    background: linear-gradient(135deg, #7C3AED 0%, #5B21B6 100%) !important;
    border: none !important;
    border-radius: 9px !important;
    color: #fff !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 12px rgba(124,58,237,0.4) !important;
    transition: all 0.22s !important;
}
[data-testid="stFormSubmitButton"] button:hover {
    box-shadow: 0 6px 20px rgba(124,58,237,0.55) !important;
    transform: translateY(-2px) !important;
}

/* Number input +/- buttons */
.stNumberInput button {
    background: #1A1730 !important;
    border-color: #2D2556 !important;
    color: #A78BFA !important;
}

/* Multiselect tags */
[data-baseweb="tag"] {
    background: rgba(124,58,237,0.2) !important;
    border: 1px solid rgba(124,58,237,0.4) !important;
    border-radius: 6px !important;
    color: #C4B5FD !important;
}

/* Tooltip */
[data-testid="stTooltipIcon"] { color: #7C3AED !important; }

/* Page link icons in sidebar */
[data-testid="stSidebar"] .stPageLink span {
    color: #A78BFA !important;
}
</style>
"""
