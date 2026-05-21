"""
Proposal Agent — generates full business proposals, LinkedIn messages, WhatsApp pitches.
"""
import json
import re
from ..services.ai_service import AIService

SYSTEM = """You are an expert B2B business proposal writer and sales strategist.
Write compelling, professional proposals that win deals.
Always respond with valid JSON only unless asked for plain text."""


class ProposalAgent:
    name = "Proposal Agent"

    def __init__(self, ai: AIService):
        self.ai = ai

    # ── Full Proposal ─────────────────────────────────────────────────────────

    def generate_proposal(self, company: dict, contact: dict,
                           sender_name: str = "BraveAspire Team",
                           sender_company: str = "BraveAspire",
                           services: str = "custom software development & AI solutions") -> dict:
        """
        Generate a full business proposal document.
        Returns dict with all sections as markdown strings.
        """
        prompt = f"""Write a comprehensive B2B business proposal.

CLIENT:
- Company: {company.get('name')}
- Industry: {company.get('industry')}
- Contact: {contact.get('name')}, {contact.get('designation')}
- Employee Size: {company.get('employee_size')}
- Pain Points: {company.get('pain_points')}
- Tech Stack: {company.get('tech_stack')}

OUR COMPANY: {sender_company}
OUR SERVICES: {services}
AUTHOR: {sender_name}

Return JSON with these proposal sections:
{{
  "title": "Proposal title",
  "executive_summary": "2-3 paragraph executive summary",
  "problem_statement": "Their specific challenges (bullet points as markdown)",
  "proposed_solution": "Our tailored solution (with subsections)",
  "why_us": "3 reasons why {sender_company} is the right choice",
  "case_study": "Brief relevant case study or example",
  "timeline": "Project timeline (markdown table: Phase | Duration | Deliverables)",
  "pricing": "Pricing options (markdown table: Package | Price | Includes)",
  "next_steps": "Clear next steps numbered list",
  "closing": "Professional closing paragraph"
}}"""

        raw    = self.ai.generate(prompt, system=SYSTEM)
        result = self._parse_json(raw)

        # Build full markdown document
        result["full_markdown"] = self._render_markdown(result, company, contact,
                                                         sender_name, sender_company)
        return result

    def _render_markdown(self, sections: dict, company: dict, contact: dict,
                          sender_name: str, sender_company: str) -> str:
        from datetime import datetime
        date = datetime.now().strftime("%B %d, %Y")
        md = f"""# {sections.get('title', f'Proposal for {company.get("name")}')}

**Prepared for:** {contact.get('name')}, {contact.get('designation')} — {company.get('name')}
**Prepared by:** {sender_name}, {sender_company}
**Date:** {date}

---

## Executive Summary
{sections.get('executive_summary', '')}

---

## Problem Statement
{sections.get('problem_statement', '')}

---

## Proposed Solution
{sections.get('proposed_solution', '')}

---

## Why {sender_company}?
{sections.get('why_us', '')}

---

## Case Study / Reference
{sections.get('case_study', '')}

---

## Project Timeline
{sections.get('timeline', '')}

---

## Investment & Pricing
{sections.get('pricing', '')}

---

## Next Steps
{sections.get('next_steps', '')}

---

## Closing
{sections.get('closing', '')}

---
*{sender_company} · Confidential Business Proposal*
"""
        return md

    # ── LinkedIn Message ──────────────────────────────────────────────────────

    def generate_linkedin_message(self, company: dict, contact: dict,
                                   sender_name: str = "BraveAspire Team") -> str:
        """
        Generate a LinkedIn connection request message (≤300 chars).
        """
        prompt = f"""Write a LinkedIn connection request message for:
Contact: {contact.get('name')}, {contact.get('designation')} at {company.get('name')}
Industry: {company.get('industry')}
Pain Point: {company.get('pain_points', '')[:100]}
Sender: {sender_name}

Rules:
- MAX 300 characters
- Professional but warm
- Mention one specific relevant thing
- No hard sell
- End with a soft reason to connect

Return ONLY the message text, no JSON, no quotes."""

        return self.ai.generate(prompt)[:300]

    # ── WhatsApp Pitch ────────────────────────────────────────────────────────

    def generate_whatsapp_pitch(self, company: dict, contact: dict,
                                 sender_name: str = "BraveAspire Team") -> str:
        """
        Generate a casual WhatsApp pitch message (≤500 chars).
        """
        prompt = f"""Write a casual WhatsApp outreach message for:
Contact: {contact.get('name')} at {company.get('name')} ({company.get('industry')})
Pain Point: {company.get('pain_points', '')[:100]}
Sender: {sender_name}

Rules:
- MAX 500 characters
- Casual, friendly tone (not corporate)
- Use 1-2 relevant emojis
- Quick value statement
- Easy yes/no CTA at the end
- Feel like it's from a real person, not a bot

Return ONLY the message text."""

        return self.ai.generate(prompt)[:500]

    # ── Email Subject Lines ───────────────────────────────────────────────────

    def generate_subject_lines(self, company: dict, count: int = 5) -> list[str]:
        """Generate A/B test subject line variants."""
        prompt = f"""Generate {count} email subject line variants for cold outreach to {company.get('name')} ({company.get('industry')}).
Pain points: {company.get('pain_points', '')}

Rules: Under 60 chars each, no spam words, personalized.
Return JSON array of strings: ["subject 1", "subject 2", ...]"""

        raw = self.ai.generate(prompt, system=SYSTEM)
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        try:
            lines = json.loads(raw)
            if isinstance(lines, list):
                return [str(s) for s in lines[:count]]
        except Exception:
            pass
        return [f"Quick question about {company.get('name', 'your company')}'s tech stack"]

    def _parse_json(self, text: str) -> dict:
        text = re.sub(r"```(?:json)?", "", text).strip()
        try:
            d = json.loads(text)
            return d if isinstance(d, dict) else {}
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return {}
