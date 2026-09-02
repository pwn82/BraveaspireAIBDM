"""
Phase 8 — agent + workflow contract tests.

Not full end-to-end (that needs a real LLM); focused on the code paths that
break silently if the agent/workflow contract shifts:

  Agents
    1. FollowUpAgent.schedule_followups persists 3 rows with the right sequence.
    2. Cross-tenant guard: schedule_followups against another org's outreach
       must produce zero rows (the underlying CRMService rejects it).
    3. detect_overdue only returns follow-ups past their scheduled_at.
    4. _quick_followup_body renders per-sequence copy.

  Workflow
    5. `create_bdm_workflow` compiles without raising and has a `stream` method
       (real LangGraph path when installed, _FallbackWorkflow otherwise).
    6. `_default_state` returns every declared field with a sensible zero-value
       so callers can trust the state shape.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["USE_SQLSERVER"] = "false"
os.environ["APP_ENV"]       = "development"
os.environ["SECRET_KEY"]    = "phase8-agent-test-secret-key-must-be-long"
os.environ["DISABLE_SCHEDULER"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.db import init_db, get_db                        # noqa: E402
from app.database.models import (
    Organization, Company, Contact, Outreach, FollowUp,
)                                                                  # noqa: E402
from app.services.crm_service import CRMService                    # noqa: E402
from app.agents.followup_agent import FollowUpAgent, FOLLOWUP_SCHEDULE  # noqa: E402
from app.workflows.bdm_workflow import (
    create_bdm_workflow, _default_state, BDMState,
)                                                                  # noqa: E402


class _StubAI:
    """AI stand-in that just echoes deterministic strings."""
    provider = "stub"
    model_name = "stub-1"
    def chat(self, messages):
        return "stub response"
    def generate(self, prompt, system=None):
        return "stub response"


def _new_org_with_contact(slug: str) -> tuple[int, int, int]:
    """Return (org_id, contact_id, outreach_id) for a fresh org."""
    with get_db() as db:
        org = Organization(name=slug, slug=slug, status="active", plan="pro")
        db.add(org); db.flush()
        oid = org.id
        co = Company(organization_id=oid, name=f"{slug} Co")
        db.add(co); db.flush()
        ct = Contact(organization_id=oid, company_id=co.id,
                     name="Contact X", email="cx@x.co")
        db.add(ct); db.flush()
        out = Outreach(
            organization_id=oid, contact_id=ct.id,
            subject="Hi X", body="Hello",
            status="Sent", sent_at=datetime.utcnow(),
            tracking_id=f"trk-{slug}",
        )
        db.add(out); db.flush()
        return oid, ct.id, out.id


class FollowUpAgentTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_schedule_creates_three_rows_with_correct_sequence(self):
        org_id, ct_id, out_id = _new_org_with_contact("agent-01")
        crm = CRMService(organization_id=org_id)
        agent = FollowUpAgent(ai=_StubAI(), crm=crm)

        result = agent.schedule_followups(
            outreach_id=out_id,
            outreach={"subject": "Hi X", "body": "Hello"},
            contact={"name": "Contact X", "email": "cx@x.co"},
            company={"name": "agent-01 Co"},
        )
        self.assertEqual(len(result), len(FOLLOWUP_SCHEDULE))

        with get_db() as db:
            rows = db.query(FollowUp).filter(FollowUp.outreach_id == out_id).all()
            self.assertEqual(len(rows), 3)
            sequences = sorted(r.sequence_number for r in rows)
            self.assertEqual(sequences, [1, 2, 3])
            for r in rows:
                # Every row must inherit the outreach's org (Phase 1 contract).
                self.assertEqual(r.organization_id, org_id)
                self.assertEqual(r.status, "Scheduled")
                self.assertIn("Hi X", r.subject or "")

    def test_02_cross_tenant_outreach_id_produces_zero_rows(self):
        # Org A owns an outreach; Org B's agent tries to schedule against it.
        org_a, _, out_a = _new_org_with_contact("agent-02a")
        org_b, _, _     = _new_org_with_contact("agent-02b")

        crm_b = CRMService(organization_id=org_b)
        agent_b = FollowUpAgent(ai=_StubAI(), crm=crm_b)

        result = agent_b.schedule_followups(
            outreach_id=out_a,
            outreach={"subject": "victim"},
            contact={"name": "n"},
            company={"name": "c"},
        )
        # add_followup returns None for cross-tenant FK — every entry is None.
        self.assertTrue(all(r is None for r in result),
                        f"cross-tenant schedule must produce Nones, got {result}")

        # And no rows landed under Org B or Org A.
        with get_db() as db:
            self.assertEqual(
                db.query(FollowUp).filter(FollowUp.organization_id == org_b).count(),
                0,
            )
            self.assertEqual(
                db.query(FollowUp).filter(
                    FollowUp.organization_id == org_a,
                    FollowUp.outreach_id     == out_a,
                ).count(),
                0,
            )

    def test_03_detect_overdue_filters_by_time(self):
        org_id, _, out_id = _new_org_with_contact("agent-03")
        with get_db() as db:
            db.add(FollowUp(organization_id=org_id, outreach_id=out_id,
                            sequence_number=1, subject="past",
                            scheduled_at=datetime.utcnow() - timedelta(days=2),
                            status="Scheduled"))
            db.add(FollowUp(organization_id=org_id, outreach_id=out_id,
                            sequence_number=2, subject="future",
                            scheduled_at=datetime.utcnow() + timedelta(days=2),
                            status="Scheduled"))

        agent = FollowUpAgent(ai=_StubAI(),
                              crm=CRMService(organization_id=org_id))
        overdue = agent.detect_overdue()
        subjects = {fu.get("subject") for fu in overdue}
        self.assertIn("past", subjects)
        self.assertNotIn("future", subjects)

    def test_04_quick_body_renders_per_sequence(self):
        agent = FollowUpAgent(ai=_StubAI(),
                              crm=CRMService(organization_id=1))
        for seq in (1, 2, 3):
            body = agent._quick_followup_body(seq, name="Jane", company="Acme")
            self.assertIn("Jane", body)
            self.assertIn("Acme", body)


class WorkflowTests(unittest.TestCase):

    def test_05_workflow_compiles_and_exposes_stream(self):
        wf = create_bdm_workflow(ai_service=_StubAI(),
                                 crm_service=CRMService(organization_id=1))
        self.assertTrue(hasattr(wf, "stream"),
                        "compiled workflow must expose a `stream` method")

    def test_06_default_state_shape(self):
        state: BDMState = _default_state()
        # A sample of required keys — cheap contract check.
        for key in (
            "query", "filters", "count",
            "companies", "analyzed_companies", "contacts", "generated_emails",
            "human_feedback", "approved_emails",
            "saved_company_ids", "sent_outreach_ids", "scheduled_followup_ids",
            "current_step", "step_logs", "errors",
        ):
            self.assertIn(key, state, f"missing key {key} in default state")
        self.assertEqual(state["errors"], [])
        self.assertEqual(state["step_logs"], [])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        try:
            os.unlink(_TEST_DB)
        except Exception:
            pass
