"""
BraveAspire LangGraph BDM Workflow
===================================
Nodes (in order):
  1. lead_discovery      — AI discovers companies
  2. company_analysis    — scores + analyzes top 3
  3. contact_finder      — AI finds decision-makers
  4. email_generator     — personalizes cold emails
  5. human_review        — HITL pause (interrupt_before)
  6. email_sender        — sends approved emails
  7. crm_updater         — saves everything to DB
  8. followup_scheduler  — creates Day 3/7/14 follow-up records

HITL usage (Streamlit):
  thread_id = str(uuid.uuid4())
  config    = {"configurable": {"thread_id": thread_id}}
  # Run until HITL pause
  for chunk in app.stream(initial_state, config, stream_mode="values"):
      ...
  # Resume after human approval
  app.update_state(config, {"human_feedback": {"approved": True, "selected": [0,1,2]}})
  for chunk in app.stream(None, config, stream_mode="values"):
      ...
"""
from __future__ import annotations
import logging
import uuid
from typing import TypedDict, Optional

logger = logging.getLogger("bdm_workflow")


# ── State ─────────────────────────────────────────────────────────────────────

class BDMState(TypedDict):
    # Inputs
    query:   str
    filters: dict
    count:   int
    sender_name:    str
    sender_company: str
    services:       str
    # Stage outputs
    companies:           list
    analyzed_companies:  list
    contacts:            list
    generated_emails:    list
    # HITL
    human_feedback:      dict          # {"approved": bool, "selected": [idx]}
    approved_emails:     list
    # Results
    saved_company_ids:   list
    sent_outreach_ids:   list
    scheduled_followup_ids: list
    # Meta
    current_step:  str
    step_logs:     list
    errors:        list


def _default_state() -> BDMState:
    return BDMState(
        query="", filters={}, count=5,
        sender_name="BraveAspire Team", sender_company="BraveAspire",
        services="custom software development & AI solutions",
        companies=[], analyzed_companies=[], contacts=[], generated_emails=[],
        human_feedback={}, approved_emails=[],
        saved_company_ids=[], sent_outreach_ids=[], scheduled_followup_ids=[],
        current_step="start", step_logs=[], errors=[],
    )


# ── Node functions ─────────────────────────────────────────────────────────────

def _lead_discovery_node(state: BDMState, ai_service, crm_service) -> dict:
    logger.info("[BDM] lead_discovery started")
    logs   = list(state.get("step_logs", []))
    errors = list(state.get("errors", []))
    logs.append("🔍 Lead Discovery: finding companies with AI...")

    companies = []

    # ── Try AI discovery first ────────────────────────────────────────────────
    try:
        from ..agents.lead_discovery_agent import LeadDiscoveryAgent
        agent = LeadDiscoveryAgent(ai_service)
        companies, _ = agent.discover(
            state["query"],
            count=state.get("count", 5),
            filters=state.get("filters", {}),
        )
        if companies:
            logs.append(f"✅ AI discovered {len(companies)} companies")
    except Exception as e:
        err_msg = f"AI lead discovery failed: {e}"
        logger.warning(err_msg)
        errors.append(err_msg)
        logs.append(f"⚠️ AI unavailable ({type(e).__name__}), switching to CRM fallback...")

    # ── Fallback: pull matching companies from existing CRM ───────────────────
    if not companies:
        try:
            query_str = state.get("query", "")
            filters   = state.get("filters", {})
            count     = state.get("count", 5)

            # Search by query keywords + optional industry filter
            crm_hits = crm_service.get_companies(
                search=query_str,
                industry=filters.get("industry", ""),
                limit=count * 3,
            )
            # Also pull all companies and take top-scored if search returned nothing
            if not crm_hits:
                crm_hits = crm_service.get_companies(limit=count * 3)

            # Convert CRM dicts into the same shape the workflow expects
            for c in crm_hits[:count]:
                companies.append({
                    "name":          c.get("name", ""),
                    "website":       c.get("website", ""),
                    "industry":      c.get("industry", "Technology"),
                    "location":      c.get("location", "USA"),
                    "employee_size": c.get("employee_size", 100),
                    "revenue":       c.get("revenue", "Unknown"),
                    "score":         c.get("score", 75),
                    "hiring_status": c.get("hiring_status", False),
                    "tech_stack":    c.get("tech_stack", ""),
                    "pain_points":   c.get("pain_points", ""),
                    "source":        c.get("source", "CRM"),
                    "status":        c.get("status", "New"),
                    "_crm_id":       c.get("id"),   # remember existing ID
                })
            if companies:
                logs.append(f"✅ CRM fallback: loaded {len(companies)} existing companies")
            else:
                logs.append("⚠️ No companies found in CRM either. Add companies first.")
        except Exception as e2:
            err_msg2 = f"CRM fallback also failed: {e2}"
            logger.error(err_msg2)
            errors.append(err_msg2)
            logs.append(f"❌ {err_msg2}")

    return {
        "companies":    companies,
        "step_logs":    logs,
        "errors":       errors,
        "current_step": "company_analysis",
    }


def _company_analysis_node(state: BDMState, ai_service, crm_service) -> dict:
    logger.info("[BDM] company_analysis started")
    logs     = list(state.get("step_logs", []))
    errors   = list(state.get("errors", []))
    companies = state.get("companies", [])[:3]
    logs.append(f"🔬 Company Analysis: scoring {len(companies)} companies in parallel...")

    if not companies:
        logs.append("⚠️ No companies to analyze")
        return {"analyzed_companies": [], "step_logs": logs, "errors": errors,
                "current_step": "contact_finder"}

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _analyze_one(company):
        try:
            from ..agents.company_analyzer_agent import CompanyAnalyzerAgent
            analysis = CompanyAnalyzerAgent(ai_service).analyze(company)
            return {**company, "ai_analysis": analysis,
                    "score": analysis.get("score", company.get("score", 70))}
        except Exception as e:
            errors.append(f"Analysis failed for {company.get('name')}: {e}")
            return {**company, "ai_analysis": {}, "score": company.get("score", 70)}

    analyzed = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_analyze_one, c): c for c in companies}
        for fut in as_completed(futures):
            analyzed.append(fut.result())

    logs.append(f"✅ Analyzed {len(analyzed)} companies")
    return {"analyzed_companies": analyzed, "step_logs": logs, "errors": errors,
            "current_step": "contact_finder"}


def _contact_finder_node(state: BDMState, ai_service, crm_service) -> dict:
    logger.info("[BDM] contact_finder started")
    logs   = list(state.get("step_logs", []))
    errors = list(state.get("errors", []))
    logs.append("👤 Contact Finder: identifying decision-makers...")
    contacts = []

    import json as _json, re as _re

    def _find_contacts_for(company):
        company_name = company.get("name", "") or "Unknown Company"
        raw_website  = company.get("website", "") or ""
        # Derive a clean domain from website URL
        website = raw_website.replace("https://","").replace("http://","").split("/")[0].strip()
        if not website:
            website = (company_name.lower().replace(" ","") + ".com") if company_name != "Unknown Company" else "company.com"
        found_cts    = []

        # ── 1. DB contacts first (instant, no AI needed) ──────────────────────
        crm_id   = company.get("_crm_id")
        existing = crm_service.get_contacts(company_id=crm_id) if crm_id else []
        if not existing:
            existing = crm_service.get_contacts(search=company_name)
        if existing:
            for c in existing[:2]:
                found_cts.append({
                    "name":         c.get("name", ""),
                    "designation":  c.get("designation", ""),
                    "email":        c.get("email", ""),
                    "linkedin":     c.get("linkedin", ""),
                    "company_id":   c.get("id"),
                    "company_name": company_name,
                    "company":      company,
                })
            return found_cts, None

        # ── 2. AI fallback — compact prompt ───────────────────────────────────
        try:
            domain = website.replace("https://","").replace("http://","").split("/")[0] or "company.com"
            prompt = (
                f"List 1-2 decision-makers for {company_name} ({company.get('industry','Tech')}).\n"
                f"Return ONLY a JSON array, no explanation:\n"
                f'[{{"name":"Jane Doe","designation":"CTO","email":"jane@{domain}","linkedin":""}}]'
            )
            raw = ai_service.generate(prompt)
            # Strip markdown fences
            raw = _re.sub(r"```(?:json)?", "", raw).strip().strip("`")
            # Extract first [...] block
            m = _re.search(r'\[.*?\]', raw, _re.DOTALL)
            raw = m.group(0) if m else raw

            parsed = _json.loads(raw)

            # Normalise: could be a dict (single item) or list
            if isinstance(parsed, dict):
                parsed = [parsed]

            for c in parsed[:2]:
                # Guard: item must be a dict — skip strings or other types
                if not isinstance(c, dict):
                    continue
                contact_entry = {
                    "name":         str(c.get("name", "Decision Maker")),
                    "designation":  str(c.get("designation", c.get("title", "CTO"))),
                    "email":        str(c.get("email", f"cto@{domain}")),
                    "linkedin":     str(c.get("linkedin", c.get("linkedin_url", ""))),
                    "company_id":   None,
                    "company_name": company_name,
                    "company":      company,
                }
                found_cts.append(contact_entry)

        except Exception as e:
            # AI failed — add a placeholder so the pipeline doesn't stall
            domain = website.replace("https://","").replace("http://","").split("/")[0] or "company.com"
            found_cts.append({
                "name":         "Decision Maker",
                "designation":  "CTO",
                "email":        f"cto@{domain}",
                "linkedin":     "",
                "company_id":   None,
                "company_name": company_name,
                "company":      company,
            })
            return found_cts, f"Contact AI failed for {company_name or 'Unknown'}: {e}"

        if not found_cts:
            # AI returned empty / unparseable — add placeholder
            domain = website.replace("https://","").replace("http://","").split("/")[0] or "company.com"
            found_cts.append({
                "name":         "Decision Maker",
                "designation":  "CTO",
                "email":        f"cto@{domain}",
                "linkedin":     "",
                "company_id":   None,
                "company_name": company_name,
                "company":      company,
            })

        return found_cts, None

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_find_contacts_for, c): c for c in state.get("analyzed_companies", [])}
        for fut in as_completed(futures):
            cts, err = fut.result()
            contacts.extend(cts)
            if err:
                errors.append(err)

    logs.append(f"✅ Found {len(contacts)} contacts")
    return {"contacts": contacts, "step_logs": logs, "errors": errors, "current_step": "email_generator"}


def _email_generator_node(state: BDMState, ai_service, crm_service) -> dict:
    logger.info("[BDM] email_generator started")
    logs   = list(state.get("step_logs", []))
    errors = list(state.get("errors", []))
    logs.append("✉️ Email Generator: personalizing cold emails...")
    emails = []

    sender_name    = state.get("sender_name",    "BraveAspire Team")
    sender_company = state.get("sender_company", "BraveAspire")
    services       = state.get("services",       "custom software development & AI solutions")

    from ..agents.personalization_agent import PersonalizationAgent
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _gen_email(contact):
        company      = contact.get("company", {})
        contact_name = contact.get("name", "there")
        company_name = company.get("name", contact.get("company_name", "your company"))
        pain_points  = company.get("pain_points", "")
        try:
            result  = PersonalizationAgent(ai_service).generate_email(
                company=company, contact=contact,
                sender_name=sender_name, sender_company=sender_company, services=services,
            )
            subject = result.get("subject", "")
            body    = result.get("body", "")
            cta     = result.get("cta", "")
        except Exception as e:
            errors.append(f"Email AI failed for {contact_name}: {e}")
            subject = f"Quick question about {company_name}'s tech roadmap"
            body = (
                f"Hi {contact_name},\n\n"
                f"I came across {company_name} and was impressed by what you're building.\n\n"
                f"At {sender_company}, we specialize in {services}. "
                + (f"We noticed: {pain_points}." if pain_points
                   else "We help companies like yours accelerate development.")
                + f"\n\nWould you have 15 minutes this week for a quick intro call?\n\n"
                f"Best regards,\n{sender_name}\n{sender_company}"
            )
            cta = "15-min intro call"
        return {"contact": contact, "company": company,
                "subject": subject, "body": body, "cta": cta, "approved": False}

    contacts_list = state.get("contacts", [])
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_gen_email, ct) for ct in contacts_list]
        for fut in as_completed(futures):
            emails.append(fut.result())

    logs.append(f"✅ Generated {len(emails)} personalized emails")
    return {"generated_emails": emails, "step_logs": logs, "errors": errors, "current_step": "human_review"}


def _human_review_node(state: BDMState, ai_service, crm_service) -> dict:
    """HITL node — LangGraph interrupts BEFORE this node."""
    logger.info("[BDM] human_review: processing feedback")
    logs     = list(state.get("step_logs", []))
    feedback = state.get("human_feedback", {})
    emails   = state.get("generated_emails", [])

    if not feedback.get("approved"):
        logs.append("⏸️ Workflow paused for human review")
        return {"step_logs": logs, "current_step": "human_review", "approved_emails": []}

    selected = feedback.get("selected", list(range(len(emails))))
    approved = [emails[i] for i in selected if i < len(emails)]
    logs.append(f"✅ Human approved {len(approved)}/{len(emails)} emails")
    return {"approved_emails": approved, "step_logs": logs, "current_step": "email_sender"}


def _email_sender_node(state: BDMState, ai_service, crm_service) -> dict:
    logger.info("[BDM] email_sender started")
    logs = list(state.get("step_logs", []))
    logs.append("📤 Email Sender: sending approved emails...")
    sent_ids = []
    try:
        import os
        from ..utils.helpers import send_email
        smtp = {
            "smtp_host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
            "smtp_port":     int(os.getenv("SMTP_PORT", "587")),
            "smtp_user":     os.getenv("SMTP_USER", ""),
            "smtp_password": os.getenv("SMTP_PASSWORD", ""),
            "from_email":    os.getenv("FROM_EMAIL", ""),
            "from_name":     os.getenv("FROM_NAME", "BraveAspire AI BDM"),
        }
        smtp_ready = bool(smtp["smtp_user"])

        for email_item in state.get("approved_emails", []):
            to = email_item.get("contact", {}).get("email", "")
            if to and smtp_ready:
                ok, _ = send_email(to, email_item["subject"], email_item["body"], smtp)
                status = "Sent" if ok else "Draft"
            else:
                status = "Draft"   # No SMTP configured — save as draft
            sent_ids.append({"email": email_item, "status": status})

        sent_count = sum(1 for s in sent_ids if s["status"] == "Sent")
        draft_count = sum(1 for s in sent_ids if s["status"] == "Draft")
        logs.append(f"✅ Sent: {sent_count}, Saved as Draft: {draft_count}")
        return {"sent_outreach_ids": sent_ids, "step_logs": logs, "current_step": "crm_updater"}
    except Exception as e:
        logs.append(f"❌ Email sender error: {e}")
        return {"sent_outreach_ids": [], "step_logs": logs,
                "errors": state.get("errors", []) + [str(e)], "current_step": "crm_updater"}


def _crm_updater_node(state: BDMState, ai_service, crm_service) -> dict:
    logger.info("[BDM] crm_updater started")
    logs = list(state.get("step_logs", []))
    logs.append("🗄️ CRM Updater: saving to database...")
    company_ids = []
    try:
        from datetime import datetime
        import uuid as _uuid

        # Save companies
        for company in state.get("analyzed_companies", []):
            existing = crm_service.get_companies(search=company.get("name", ""))
            if not existing:
                saved = crm_service.add_company({
                    "name": company.get("name",""), "website": company.get("website",""),
                    "industry": company.get("industry",""), "location": company.get("location",""),
                    "employee_size": company.get("employee_size",0), "score": company.get("score",70),
                    "status": "New", "hiring_status": company.get("hiring_status",False),
                    "tech_stack": company.get("tech_stack",""),
                    "pain_points": company.get("pain_points",""), "source": "AI Workflow",
                })
                company_ids.append(saved["id"])

        # Save outreach records
        for item in state.get("sent_outreach_ids", []):
            email_item = item.get("email", {})
            contact    = email_item.get("contact", {})
            status     = item.get("status", "Draft")
            # Find or create contact in DB
            contacts = crm_service.get_contacts(search=contact.get("name", ""))
            if contacts:
                contact_id = contacts[0]["id"]
            else:
                company_name = contact.get("company_name", "")
                companies    = crm_service.get_companies(search=company_name)
                company_id   = companies[0]["id"] if companies else (company_ids[0] if company_ids else None)
                if company_id:
                    saved_ct = crm_service.add_contact({
                        "company_id": company_id, "name": contact.get("name",""),
                        "designation": contact.get("designation",""),
                        "email": contact.get("email",""), "verified": False,
                    })
                    contact_id = saved_ct["id"]
                else:
                    continue

            crm_service.create_outreach({
                "contact_id": contact_id,
                "subject":    email_item.get("subject",""),
                "body":       email_item.get("body",""),
                "status":     status,
                "sent_at":    datetime.utcnow() if status == "Sent" else None,
                "tracking_id": str(_uuid.uuid4()),
            })

        logs.append(f"✅ Saved {len(company_ids)} companies + {len(state.get('sent_outreach_ids',[]))} outreach records")
        return {"saved_company_ids": company_ids, "step_logs": logs, "current_step": "followup_scheduler"}
    except Exception as e:
        logs.append(f"❌ CRM updater error: {e}")
        return {"saved_company_ids": [], "step_logs": logs,
                "errors": state.get("errors", []) + [str(e)], "current_step": "followup_scheduler"}


def _followup_scheduler_node(state: BDMState, ai_service, crm_service) -> dict:
    logger.info("[BDM] followup_scheduler started")
    logs = list(state.get("step_logs", []))
    logs.append("🔁 Follow-up Scheduler: scheduling Day 3/7/14 follow-ups...")
    fu_ids = []
    try:
        from ..agents.followup_agent import FollowUpAgent
        from datetime import datetime, timedelta
        fu_agent = FollowUpAgent(ai_service, crm_service)
        outreach_list = crm_service.get_outreach(status="Sent")
        for o in outreach_list[-len(state.get("sent_outreach_ids", [])):]:
            contacts = crm_service.get_contacts(company_id=None)
            contact  = next((c for c in contacts if c["id"] == o.get("contact_id")), {})
            company  = {}
            fus      = fu_agent.schedule_followups(o["id"], o, contact, company)
            fu_ids.extend([f["id"] for f in fus])
        logs.append(f"✅ Scheduled {len(fu_ids)} follow-up emails")
        logs.append("🎉 BDM Workflow complete!")
        return {"scheduled_followup_ids": fu_ids, "step_logs": logs, "current_step": "complete"}
    except Exception as e:
        logs.append(f"❌ Follow-up scheduler error: {e}")
        logs.append("🎉 Workflow finished (with some errors)")
        return {"scheduled_followup_ids": [], "step_logs": logs,
                "errors": state.get("errors", []) + [str(e)], "current_step": "complete"}


# ── Graph factory ─────────────────────────────────────────────────────────────

def create_bdm_workflow(ai_service, crm_service):
    """
    Build and return the compiled LangGraph BDM workflow.
    Uses MemorySaver for HITL pause/resume.
    """
    try:
        from langgraph.graph import StateGraph, END, START
        from langgraph.checkpoint.memory import MemorySaver

        def ld(s):   return _lead_discovery_node(s, ai_service, crm_service)
        def ca(s):   return _company_analysis_node(s, ai_service, crm_service)
        def cf(s):   return _contact_finder_node(s, ai_service, crm_service)
        def eg(s):   return _email_generator_node(s, ai_service, crm_service)
        def hr(s):   return _human_review_node(s, ai_service, crm_service)
        def es(s):   return _email_sender_node(s, ai_service, crm_service)
        def cu(s):   return _crm_updater_node(s, ai_service, crm_service)
        def fs(s):   return _followup_scheduler_node(s, ai_service, crm_service)

        graph = StateGraph(BDMState)
        graph.add_node("lead_discovery",       ld)
        graph.add_node("company_analysis",     ca)
        graph.add_node("contact_finder",       cf)
        graph.add_node("email_generator",      eg)
        graph.add_node("human_review",         hr)
        graph.add_node("email_sender",         es)
        graph.add_node("crm_updater",          cu)
        graph.add_node("followup_scheduler",   fs)

        graph.set_entry_point("lead_discovery")
        graph.add_edge("lead_discovery",     "company_analysis")
        graph.add_edge("company_analysis",   "contact_finder")
        graph.add_edge("contact_finder",     "email_generator")
        graph.add_edge("email_generator",    "human_review")
        graph.add_edge("human_review",       "email_sender")
        graph.add_edge("email_sender",       "crm_updater")
        graph.add_edge("crm_updater",        "followup_scheduler")
        graph.add_edge("followup_scheduler", END)

        memory = MemorySaver()
        app    = graph.compile(checkpointer=memory, interrupt_before=["human_review"])
        logger.info("LangGraph BDM workflow compiled successfully.")
        return app

    except ImportError as e:
        logger.warning(f"LangGraph not available: {e}. Using fallback sequential runner.")
        return _FallbackWorkflow(ai_service, crm_service)


class _FallbackWorkflow:
    """
    Synchronous fallback when LangGraph is not installed.
    Same interface as compiled LangGraph app.
    """
    def __init__(self, ai_service, crm_service):
        self._ai  = ai_service
        self._crm = crm_service
        self._state: dict = {}

    def stream(self, state_or_none, config=None, stream_mode="values"):
        if state_or_none is None:
            state = self._state
        else:
            state = {**_default_state(), **state_or_none}
        nodes = [
            ("lead_discovery",     _lead_discovery_node),
            ("company_analysis",   _company_analysis_node),
            ("contact_finder",     _contact_finder_node),
            ("email_generator",    _email_generator_node),
        ]
        for name, fn in nodes:
            update = fn(state, self._ai, self._crm)
            state  = {**state, **update}
            yield {name: state}
        self._state = state

    def stream_after_hitl(self, config=None):
        state = self._state
        nodes = [
            ("human_review",       _human_review_node),
            ("email_sender",       _email_sender_node),
            ("crm_updater",        _crm_updater_node),
            ("followup_scheduler", _followup_scheduler_node),
        ]
        for name, fn in nodes:
            update = fn(state, self._ai, self._crm)
            state  = {**state, **update}
            yield {name: state}
        self._state = state

    def get_state(self, config=None):
        class _S:
            values = {}
        s        = _S()
        s.values = self._state
        return s

    def update_state(self, config, update: dict):
        self._state = {**self._state, **update}
