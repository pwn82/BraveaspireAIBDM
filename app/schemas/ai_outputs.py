"""
Typed contracts for every agent's AI output (P0 hardening).

Before this, agents parsed raw AI text with `json.loads` + a regex fallback
and, on any parse failure, silently returned a hardcoded generic response —
so a malformed or hallucinated AI response was indistinguishable from a
genuine one anywhere downstream. Every schema here is passed to
`AIGateway.generate_json(schema=...)`, which validates + auto-repairs once,
then surfaces a real `schema_invalid` status on failure instead of silently
substituting fake content.

Keep these schemas permissive on the fields that are genuinely free-text
(no enum you'd have to keep in sync with prompt wording) and strict on the
fields that gate a decision (score bounds, required-ness).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, conint, confloat


class CompanyAnalysis(BaseModel):
    score: conint(ge=0, le=100) = Field(description="ICP fit score, 0-100")
    score_reason: str = Field(description="One-sentence justification for the score")
    pain_points: list[str] = Field(default_factory=list)
    services_to_pitch: list[str] = Field(default_factory=list)
    approach_angle: str = ""
    urgency: str = Field(default="Medium", description="Low | Medium | High")
    decision_maker_title: str = "CTO"
    estimated_deal_size: str = "Unknown"


class LeadDiscoveryCompany(BaseModel):
    name: str
    website: str = ""
    industry: str = "Technology"
    location: str = "Unknown"
    employee_size: conint(ge=0) = 0
    revenue: str = "Unknown"
    score: conint(ge=0, le=100) = 50
    hiring_status: bool = False
    tech_stack: str = ""
    pain_points: str = ""
    confidence: confloat(ge=0.0, le=1.0) = Field(
        default=0.5,
        description="How confident you are this is a real, currently-operating company",
    )


class LeadDiscoveryResult(BaseModel):
    companies: list[LeadDiscoveryCompany] = Field(default_factory=list)


class ContactCandidate(BaseModel):
    name: str = ""
    designation: str = "Decision Maker"
    # Deliberately NO email field — see app/policies/outreach_policy.py.
    # This agent must never emit an email address; the caller hardcodes
    # email_status="inferred" for every candidate it returns regardless.


class ContactCandidateList(BaseModel):
    contacts: list[ContactCandidate] = Field(default_factory=list)


class PersonalizedEmail(BaseModel):
    subject: str
    body: str
    cta: str = ""
    personalization_evidence: list[str] = Field(
        default_factory=list,
        description="Specific facts from the company/contact context used to personalize this email",
    )


class InboxClassification(BaseModel):
    type: str = Field(description="positive | negative | neutral | ooo | referral | question")
    sentiment: str = Field(default="neutral", description="positive | negative | neutral")
    next_action: str = "Review manually"
    suggested_response: str = ""
    urgency: str = Field(default="medium", description="low | medium | high")
    key_points: list[str] = Field(default_factory=list)


class FollowUpDecision(BaseModel):
    """Whether/how to send the next follow-up in a sequence."""
    action: str = Field(description="FOLLOW_UP | STOP_SEQUENCE")
    reason: str = ""
    body: Optional[str] = None
