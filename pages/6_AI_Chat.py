import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
from app.database.db import init_db
from app.services.crm_service import CRMService
from app.utils.helpers import load_settings, get_ai_service

st.set_page_config(page_title="AI Chat — BraveAspire", page_icon="💬", layout="wide")
_apply_theme()
init_db()
load_settings(st)

from app.utils.rbac import require_auth, require_permission
_current_user = require_auth()
require_permission("ai_chat.use", _current_user)

crm = CRMService()

# ── Extra CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.page-title{font-size:1.75rem;font-weight:700;color:#F0EEFF;margin:0}
.page-sub{font-size:.85rem;color:#9B8FD4;margin:.2rem 0 1.2rem 0;
  padding-bottom:1.2rem;border-bottom:1px solid #2D2556}
.chat-wrapper{display:flex;flex-direction:column;gap:0}
.msg-user{display:flex;justify-content:flex-end;margin-bottom:.75rem}
.msg-ai{display:flex;justify-content:flex-start;margin-bottom:.75rem}
.bubble-user{background:linear-gradient(135deg,#7C3AED,#5B21B6);color:#fff;
  border-radius:18px 18px 4px 18px;padding:.75rem 1.1rem;max-width:75%;
  font-size:.9rem;line-height:1.5;box-shadow:0 2px 12px rgba(124,58,237,.3)}
.bubble-ai{background:#1A1830;border:1px solid #2D2556;color:#E2E0F0;
  border-radius:18px 18px 18px 4px;padding:.75rem 1.1rem;max-width:80%;
  font-size:.9rem;line-height:1.5}
.ai-avatar{width:32px;height:32px;border-radius:50%;
  background:linear-gradient(135deg,#7C3AED,#4C1D95);
  display:flex;align-items:center;justify-content:center;
  font-size:.9rem;flex-shrink:0;margin-right:.6rem;margin-top:.1rem}
.user-avatar{width:32px;height:32px;border-radius:50%;background:#2D2556;
  display:flex;align-items:center;justify-content:center;
  font-size:.9rem;flex-shrink:0;margin-left:.6rem;margin-top:.1rem}
.suggestion-chip{display:inline-block;background:#1A1830;border:1px solid #4C1D95;
  border-radius:20px;padding:4px 14px;font-size:.78rem;color:#C4B5FD;
  cursor:pointer;margin:.2rem;transition:all .2s}
.suggestion-chip:hover{background:#2D2556;border-color:#7C3AED;color:#E2E0F0}
.sidebar-stat{display:flex;justify-content:space-between;align-items:center;
  padding:.4rem 0;border-bottom:1px solid #2D2556;font-size:.82rem}
.stat-name{color:#9B8FD4}
.stat-num{color:#C4B5FD;font-weight:700}
.welcome-card{background:linear-gradient(135deg,#1A1040,#12102A);
  border:1px solid #4C1D95;border-radius:12px;padding:1.5rem;
  text-align:center;margin:2rem auto;max-width:600px}
</style>
""", unsafe_allow_html=True)

# ── Page header ───────────────────────────────────────────────────────────────
col_hdr, col_clear = st.columns([8, 1])
with col_hdr:
    st.markdown('<div class="page-title">💬 AI Chat Assistant</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Ask about your leads, pipeline, or request AI-generated content</div>',
                unsafe_allow_html=True)
with col_clear:
    st.write("")
    if st.button("🗑️ Clear", key="clear_chat_top"):
        st.session_state.chat_history = []
        st.session_state.pop("pending_query", None)
        st.rerun()

# ── Sidebar context panel ─────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="font-size:.85rem;font-weight:700;color:#C4B5FD;
      text-transform:uppercase;letter-spacing:.06em;margin-bottom:.6rem">
      📊 Live CRM Context
    </div>""", unsafe_allow_html=True)

    stats = crm.get_pipeline_stats()
    for label, value in [
        ("Companies",  stats["total_companies"]),
        ("Contacts",   stats["total_contacts"]),
        ("Emails Sent",stats["emails_sent"]),
        ("Open Rate",  f"{stats['open_rate']}%"),
        ("Reply Rate", f"{stats['reply_rate']}%"),
        ("Won Deals",  stats["pipeline"].get("Won", 0)),
    ]:
        st.markdown(f"""
        <div class="sidebar-stat">
          <span class="stat-name">{label}</span>
          <span class="stat-num">{value}</span>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)
    ai_svc = get_ai_service(st)
    try:
        ok, _ = ai_svc.is_available()
    except Exception:
        ok = False
    status_col = "#34D399" if ok else "#F87171"
    status_txt = "Online" if ok else "Offline"
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:.5rem;margin-top:.5rem;
      font-size:.82rem;color:{status_col}">
      <span style="width:8px;height:8px;background:{status_col};border-radius:50%;
        display:inline-block"></span>
      {ai_svc.provider_label} · {status_txt}
    </div>""", unsafe_allow_html=True)

# ── Suggestions ───────────────────────────────────────────────────────────────
SUGGESTIONS = [
    "Show me the hottest leads right now",
    "Which industries have the most companies?",
    "How is our email campaign performing?",
    "Write a follow-up for a company that didn't reply",
    "What's our current pipeline status?",
    "Suggest 3 strategies to improve reply rate",
    "Which companies are actively hiring?",
    "Generate a value proposition for a fintech startup",
]

# ── Session state ─────────────────────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ── CRM context builder ───────────────────────────────────────────────────────
def build_crm_context() -> str:
    st_data   = crm.get_pipeline_stats()
    companies = crm.get_companies()[:10]
    outreach  = crm.get_outreach()[:5]

    top_cos = "\n".join([
        f"- {c['name']} ({c.get('industry','?')}, score {c.get('score','?')}, "
        f"status: {c.get('status','?')})"
        for c in companies
    ])
    recent_out = "\n".join([
        f"- {o.get('contact_name','?')} @ {o.get('company_name','?')}: {o.get('status','?')}"
        for o in outreach
    ])

    return f"""You are an expert AI BDM (Business Development Manager) assistant for BraveAspire.
You have real-time access to the CRM data below. Be specific, data-driven, and actionable.

CRM SNAPSHOT:
- Companies: {st_data['total_companies']} total | Pipeline: {st_data['pipeline']}
- Contacts: {st_data['total_contacts']}
- Emails: {st_data['emails_sent']} sent, {st_data['emails_opened']} opened, {st_data['emails_replied']} replied
- Open rate: {st_data['open_rate']}% | Reply rate: {st_data['reply_rate']}%

TOP COMPANIES:
{top_cos}

RECENT OUTREACH:
{recent_out}

Instructions:
- Reference real data when answering pipeline questions
- For content generation (emails, follow-ups), produce ready-to-use copy
- Be concise: lead with the answer, then explain
- Use markdown formatting for clarity"""

# ── Render chat history ───────────────────────────────────────────────────────
if not st.session_state.chat_history:
    # Welcome / empty state
    st.markdown("""
    <div class="welcome-card">
      <div style="font-size:2.2rem;margin-bottom:.5rem">🤖</div>
      <div style="font-size:1.1rem;font-weight:700;color:#C4B5FD;margin-bottom:.4rem">
        BraveAspire AI Assistant
      </div>
      <div style="font-size:.85rem;color:#9B8FD4;margin-bottom:1rem">
        Ask me anything about your pipeline, leads, or outreach — or click a suggestion below.
      </div>
    </div>""", unsafe_allow_html=True)

    # Suggestion chips rendered as buttons
    cols = st.columns(4)
    for i, suggestion in enumerate(SUGGESTIONS):
        with cols[i % 4]:
            if st.button(suggestion, key=f"sug_{i}", use_container_width=True):
                st.session_state.pending_query = suggestion
                st.rerun()
else:
    # Chat bubbles
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f"""
            <div class="msg-user">
              <div class="bubble-user">{msg["content"]}</div>
              <div class="user-avatar">👤</div>
            </div>""", unsafe_allow_html=True)
        else:
            # Use st.chat_message for AI so markdown renders properly
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(msg["content"])

    # Show suggestions again after conversation
    with st.expander("💡 Suggested follow-ups", expanded=False):
        cols = st.columns(4)
        for i, suggestion in enumerate(SUGGESTIONS):
            with cols[i % 4]:
                if st.button(suggestion, key=f"sug_after_{i}", use_container_width=True):
                    st.session_state.pending_query = suggestion
                    st.rerun()

# ── Chat input ────────────────────────────────────────────────────────────────
pending    = st.session_state.pop("pending_query", None)
user_input = st.chat_input("Ask about your leads, pipeline, or request AI content...") or pending

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})

    ai_svc        = get_ai_service(st)
    system_prompt = build_crm_context()

    messages = [{"role": "system", "content": system_prompt}]
    for msg in st.session_state.chat_history[-8:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    with st.spinner(f"Thinking with {ai_svc.provider_label}..."):
        response = ai_svc.chat(messages)

    st.session_state.chat_history.append({"role": "assistant", "content": response})
    st.rerun()
