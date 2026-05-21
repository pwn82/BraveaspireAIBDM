import sys, os, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.theme import apply_theme as _apply_theme

import streamlit as st
from app.database.db import init_db
from app.services.crm_service import CRMService
from app.utils.helpers import load_settings, get_ai_service

st.set_page_config(page_title="AI Workflow — BraveAspire", page_icon="🔄", layout="wide")
_apply_theme()
init_db()
load_settings(st)

from app.utils.rbac import require_auth, require_permission
_current_user = require_auth()
require_permission("workflow.run", _current_user)

crm = CRMService()
st.title("🔄 LangGraph BDM Workflow")
st.caption("Full automated pipeline: Discover → Analyze → Find Contacts → Generate Emails → HITL Approve → Send → CRM → Follow-ups")

# ── Pipeline diagram ──────────────────────────────────────────────────────────
with st.expander("Pipeline Architecture", expanded=False):
    st.markdown("""
```
Lead Discovery → Company Analysis → Contact Finder → Email Generator
                                                           ↓
                                              ⏸️ HUMAN REVIEW (HITL)
                                                           ↓
                                    Email Sender → CRM Updater → Follow-up Scheduler
```
**LangGraph** orchestrates each node with full state management and checkpoint-based HITL pause/resume.
""")

st.divider()

# ── AI status banner ──────────────────────────────────────────────────────────
def _check_ai(st_obj):
    ai = get_ai_service(st_obj)
    try:
        ok, _ = ai.is_available()
    except Exception:
        ok = False
    return ai, ok

_ai_check, _ai_ok = _check_ai(st)
provider_label = _ai_check.provider_label
if _ai_ok:
    st.success(f"✅ AI ready: **{provider_label}**")
else:
    st.warning(
        f"⚠️ **{provider_label}** is not reachable. "
        "Lead Discovery will fall back to existing CRM companies. "
        "Go to **Settings → AI** to configure Ollama or add a Groq API key."
    )

st.divider()

# ── Configuration ─────────────────────────────────────────────────────────────
st.subheader("1. Configure Workflow")
col_q, col_c = st.columns([4, 1])
with col_q:
    query = st.text_input(
        "What leads are you looking for?",
        placeholder="SaaS companies with 50-200 employees hiring Python engineers",
    )
with col_c:
    count = st.number_input("Leads", min_value=2, max_value=10, value=3)

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1: f_industry = st.text_input("Industry filter", placeholder="Fintech, Healthcare...")
with col_f2: f_location = st.text_input("Location filter", placeholder="USA, London...")
with col_f3: f_size     = st.text_input("Size filter",     placeholder="50-200 employees")

col_s1, col_s2 = st.columns(2)
with col_s1:
    sender_name    = st.text_input("Your Name",    value=st.session_state.get("sender_name",    "BraveAspire Team"))
with col_s2:
    sender_company = st.text_input("Your Company", value=st.session_state.get("sender_company", "BraveAspire"))
services = st.text_input(
    "Services you offer",
    value=st.session_state.get("services_offered", "custom software development & AI solutions"),
)

st.divider()

# ── Session state init ────────────────────────────────────────────────────────
for _k, _v in [
    ("wf_state",     None),
    ("wf_thread_id", None),
    ("wf_phase",     "idle"),
    ("wf_app",       None),
    ("wf_logs",      []),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

NODE_ICONS = {
    "lead_discovery":     "🔍",
    "company_analysis":   "🔬",
    "contact_finder":     "👤",
    "email_generator":    "✉️",
    "human_review":       "⏸️",
    "email_sender":       "📤",
    "crm_updater":        "🗄️",
    "followup_scheduler": "🔁",
}

# ── Run workflow ──────────────────────────────────────────────────────────────
st.subheader("2. Run Pipeline")

col_run, col_reset = st.columns([3, 1])
with col_run:
    run_btn = st.button(
        "▶ Run Full BDM Pipeline",
        type="primary",
        disabled=(not query or st.session_state.wf_phase not in ("idle", "complete")),
    )
with col_reset:
    if st.button("Reset", disabled=st.session_state.wf_phase == "idle"):
        for _k in ("wf_state", "wf_thread_id", "wf_app", "wf_logs"):
            st.session_state[_k] = None if _k != "wf_logs" else []
        st.session_state.wf_phase = "idle"
        st.rerun()

if run_btn and query:
    ai = get_ai_service(st)
    wf = st.session_state.wf_app
    if wf is None:
        with st.spinner("Building workflow graph..."):
            from app.workflows.bdm_workflow import create_bdm_workflow
            wf = create_bdm_workflow(ai, crm)
            st.session_state.wf_app = wf

    thread_id = str(uuid.uuid4())
    st.session_state.wf_thread_id = thread_id
    config = {"configurable": {"thread_id": thread_id}}

    initial = {
        "query":          query,
        "filters":        {k: v for k, v in {
                              "industry":     f_industry,
                              "location":     f_location,
                              "employee_size": f_size,
                          }.items() if v},
        "count":          int(count),
        "sender_name":    sender_name,
        "sender_company": sender_company,
        "services":       services,
        # empty defaults
        "companies": [], "analyzed_companies": [], "contacts": [],
        "generated_emails": [], "human_feedback": {}, "approved_emails": [],
        "saved_company_ids": [], "sent_outreach_ids": [], "scheduled_followup_ids": [],
        "current_step": "start", "step_logs": [], "errors": [],
    }

    st.subheader("Pipeline Progress")
    progress_box    = st.empty()
    log_box         = st.empty()
    timer_box       = st.empty()
    completed_nodes = []
    node_times      = {}          # node_name -> elapsed seconds
    accumulated     = dict(initial)

    import time as _time

    STEP_ORDER = ["lead_discovery", "company_analysis", "contact_finder",
                  "email_generator", "human_review"]

    def _render_progress(completed, active=""):
        parts = []
        for n in STEP_ORDER:
            icon  = NODE_ICONS.get(n, "•")
            label = n.replace("_", " ").title()
            elapsed = node_times.get(n)
            time_str = f" ({elapsed:.0f}s)" if elapsed else ""
            if n in completed:
                parts.append(f"**✅ {icon} {label}{time_str}**")
            elif n == active:
                parts.append(f"**⏳ {icon} {label}...**")
            else:
                parts.append(f"⬜ {icon} {label}")
        progress_box.markdown("  →  ".join(parts))

    try:
        pipeline_start = _time.time()
        active_node    = ""
        active_start   = _time.time()

        for chunk in wf.stream(initial, config):
            # ── Skip the __interrupt__ sentinel LangGraph 1.x injects ──
            if "__interrupt__" in chunk:
                continue

            node_name = list(chunk.keys())[0]

            # Record timing for the node that just finished
            if active_node and active_node not in node_times:
                node_times[active_node] = _time.time() - active_start

            completed_nodes.append(node_name)
            active_node  = node_name
            active_start = _time.time()

            # Merge partial node updates into our accumulated full state
            node_updates = chunk[node_name]
            if isinstance(node_updates, dict):
                accumulated = {**accumulated, **node_updates}

            logs = accumulated.get("step_logs", [])
            _render_progress(completed_nodes, node_name)
            log_box.markdown(
                "\n".join(f"  {l}" for l in logs[-6:]) or "_Waiting..._"
            )
            elapsed_total = _time.time() - pipeline_start
            timer_box.caption(f"Total elapsed: {elapsed_total:.0f}s")

        # ── Save state for the HITL section ──────────────────────────────────
        try:
            saved = wf.get_state(config)
            st.session_state.wf_state = dict(saved.values)
        except Exception:
            st.session_state.wf_state = accumulated

        st.session_state.wf_logs  = accumulated.get("step_logs", [])
        st.session_state.wf_phase = "awaiting_hitl"
        st.rerun()

    except Exception as e:
        import traceback
        st.error(f"Workflow error: {e}")
        st.code(traceback.format_exc(), language="text")
        st.session_state.wf_phase = "idle"

# ── Show live progress when already ran ──────────────────────────────────────
if st.session_state.wf_phase in ("awaiting_hitl", "complete") and st.session_state.wf_logs:
    with st.expander("📋 Pipeline Log", expanded=False):
        for log in st.session_state.wf_logs:
            st.markdown(f"  {log}")

# ── HITL Section ──────────────────────────────────────────────────────────────
if st.session_state.wf_phase == "awaiting_hitl":
    state  = st.session_state.wf_state or {}
    emails = state.get("generated_emails", [])
    errors = state.get("errors", [])

    if errors:
        with st.expander("⚠️ Pipeline warnings", expanded=True):
            for err in errors:
                st.warning(err)

    if not emails:
        st.warning(
            "⚠️ No emails were generated. This usually means:\n"
            "- **Ollama** is not running (start it with `ollama serve`), or\n"
            "- **No leads matched** your query.\n\n"
            "Try switching to Groq in **Settings → AI**, or broaden your query."
        )
        companies = state.get("analyzed_companies", [])
        if companies:
            st.info(f"Found {len(companies)} companies but no contacts/emails were generated.")
            for c in companies:
                st.markdown(f"- **{c.get('name')}** ({c.get('industry')}) — score {c.get('score', '?')}")
        if st.button("↩ Reset & try again"):
            for _k in ("wf_state", "wf_thread_id", "wf_app", "wf_logs"):
                st.session_state[_k] = None if _k != "wf_logs" else []
            st.session_state.wf_phase = "idle"
            st.rerun()
    else:
        st.success(f"✅ Pipeline paused for Human Review. **{len(emails)}** email(s) ready.")
        st.subheader("3. Review & Approve Emails (HITL)")
        st.caption("Check, edit, then click Send Approved.")

        selected_indices = []
        for i, em in enumerate(emails):
            contact = em.get("contact", {})
            company = em.get("company", {})
            with st.expander(
                f"📧 Email #{i+1}: {contact.get('name','?')} @ {company.get('name','?')}",
                expanded=True,
            ):
                if st.checkbox(f"Approve email #{i+1}", value=True, key=f"approve_cb_{i}"):
                    selected_indices.append(i)
                em["subject"] = st.text_input("Subject", value=em.get("subject", ""), key=f"subj_{i}")
                em["body"]    = st.text_area("Body", value=em.get("body", ""), height=180, key=f"body_{i}")
                if em.get("cta"):
                    st.info(f"**CTA:** {em['cta']}")

        col_approve, col_reject = st.columns(2)
        with col_approve:
            if st.button("✅ Send Approved Emails", type="primary", disabled=not selected_indices):
                ai     = get_ai_service(st)
                wf     = st.session_state.wf_app
                config = {"configurable": {"thread_id": st.session_state.wf_thread_id}}

                feedback = {"approved": True, "selected": selected_indices}
                try:
                    wf.update_state(config, {"human_feedback": feedback, "generated_emails": emails})
                except Exception:
                    if hasattr(wf, "_state"):
                        wf._state["human_feedback"]   = feedback
                        wf._state["generated_emails"] = emails

                post_nodes = []
                with st.spinner("Sending emails and updating CRM..."):
                    try:
                        for chunk in wf.stream(None, config):
                            if "__interrupt__" in chunk:
                                continue
                            node_name = list(chunk.keys())[0]
                            post_nodes.append(node_name)
                            st.write(f"{NODE_ICONS.get(node_name,'•')} {node_name.replace('_',' ').title()} ✅")
                    except Exception:
                        if hasattr(wf, "stream_after_hitl"):
                            for chunk in wf.stream_after_hitl(config):
                                if "__interrupt__" in chunk:
                                    continue
                                node_name = list(chunk.keys())[0]
                                st.write(f"{NODE_ICONS.get(node_name,'•')} {node_name.replace('_',' ').title()} ✅")

                # Save final state
                try:
                    final = wf.get_state(config)
                    st.session_state.wf_state = dict(final.values)
                    st.session_state.wf_logs  = list(final.values.get("step_logs", []))
                except Exception:
                    pass

                st.balloons()
                st.success("🎉 Workflow complete! Companies, contacts, outreach, and follow-ups saved to CRM.")
                st.session_state.wf_phase = "complete"
                st.rerun()

        with col_reject:
            if st.button("❌ Reject All — Regenerate"):
                for _k in ("wf_state", "wf_thread_id", "wf_app", "wf_logs"):
                    st.session_state[_k] = None if _k != "wf_logs" else []
                st.session_state.wf_phase = "idle"
                st.info("Workflow reset. Adjust your query and run again.")
                st.rerun()

# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state.wf_phase == "complete":
    state  = st.session_state.wf_state or {}
    errors = state.get("errors", [])
    st.divider()
    st.subheader("4. Workflow Results")

    col_l, col_e = st.columns([3, 1])
    with col_l:
        st.markdown("**Full Step Log:**")
        for log in st.session_state.wf_logs:
            st.markdown(f"  {log}")
    with col_e:
        if errors:
            st.warning("Warnings:")
            for e in errors:
                st.caption(e)

    st.info("Go to **Companies**, **Outreach**, and **Follow-ups** pages to see saved data.")
