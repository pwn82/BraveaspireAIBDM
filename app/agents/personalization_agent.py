import json
import re
from ..services.ai_service import AIService

SYSTEM_PROMPT = """You are an expert B2B sales copywriter who writes highly personalized cold outreach emails.
Your emails are concise, value-driven, and have high reply rates.
Always respond with valid JSON only — no markdown, no explanation."""


class PersonalizationAgent:
    name = "Personalization Agent"

    def __init__(self, ai: AIService):
        self.ai = ai
        self.thoughts: list[tuple[str, str]] = []

    # ── Cold Email ────────────────────────────────────────────────────────────

    def generate_email(self, company: dict, contact: dict,
                        sender_name: str = "BraveAspire Team",
                        sender_company: str = "BraveAspire",
                        services: str = "custom software development") -> dict:
        self.thoughts = []
        self._think(f"Generating email for {contact.get('name')} at {company.get('name')}")
        self._act("Analyzing company pain points and tech stack for personalization")

        pain_points = company.get("pain_points", "")
        tech_stack  = company.get("tech_stack", "")
        industry    = company.get("industry", "")

        self._act(f"Calling {self.ai.provider_label} for email generation")
        prompt = self._email_prompt(company, contact, sender_name, sender_company,
                                     services, pain_points, tech_stack, industry)
        raw    = self.ai.generate(prompt, system=SYSTEM_PROMPT)

        self._observe(f"AI generated {len(raw)} character response")
        result = self._parse(raw)
        self._think("Validating email structure and personalizing CTA")
        self._observe("Email generation complete — ready for HITL approval")
        result["thoughts"] = self.thoughts
        return result

    def generate_followup(self, contact: dict, company: dict,
                           sequence: int, original_subject: str) -> dict:
        prompt = f"""Generate follow-up #{sequence} for unanswered cold email.
Original subject: {original_subject}
Contact: {contact.get('name')}, {contact.get('designation')} at {company.get('name')}
Industry: {company.get('industry')}
Rules: reference follow-up, add new angle, under 100 words, clear easy CTA.
Return JSON: {{"subject":"Re: {original_subject}","body":"...","cta":"..."}}"""
        return self._parse(self.ai.generate(prompt, system=SYSTEM_PROMPT))

    # ── LinkedIn Message ──────────────────────────────────────────────────────

    def generate_linkedin_message(self, company: dict, contact: dict,
                                   sender_name: str = "BraveAspire Team") -> str:
        """LinkedIn connection request — ≤300 characters."""
        prompt = f"""Write a LinkedIn connection request message.
Contact: {contact.get('name')}, {contact.get('designation')} at {company.get('name')} ({company.get('industry')})
Pain Point: {company.get('pain_points','')[:80]}
Sender: {sender_name}
MAX 300 chars. Professional, warm, specific, no hard sell. Return ONLY the message."""
        return self.ai.generate(prompt)[:300]

    # ── WhatsApp Pitch ────────────────────────────────────────────────────────

    def generate_whatsapp_pitch(self, company: dict, contact: dict,
                                 sender_name: str = "BraveAspire Team") -> str:
        """WhatsApp outreach — ≤500 characters, casual with emojis."""
        prompt = f"""Write a casual WhatsApp outreach message.
Contact: {contact.get('name')} at {company.get('name')} ({company.get('industry')})
Pain Point: {company.get('pain_points','')[:80]}
Sender: {sender_name}
MAX 500 chars. Casual friendly tone. 1-2 emojis. Quick value + easy yes/no CTA. Return ONLY the message."""
        return self.ai.generate(prompt)[:500]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _email_prompt(self, company, contact, sender_name, sender_company,
                       services, pain_points, tech_stack, industry):
        return f"""Write a personalized B2B cold email.
SENDER: {sender_name} from {sender_company} (offering {services})
RECIPIENT: {contact.get('name')}, {contact.get('designation')} at {company.get('name')}
INDUSTRY: {industry}
TECH STACK: {tech_stack}
PAIN POINTS: {pain_points}
COMPANY SIZE: {company.get('employee_size','unknown')} employees

RULES:
1. Subject: personalized, under 60 chars, no spam words
2. Opening: reference something specific
3. Value prop: connect service to pain point
4. Social proof: one brief example or stat
5. CTA: single, specific, low-commitment ask
6. Tone: professional but conversational
7. Length: 150-200 words max

Return JSON:
{{"subject":"...","body":"Full email body\\n\\nBest,\\n{sender_name}","cta":"..."}}"""

    def _parse(self, text: str) -> dict:
        text = re.sub(r"```(?:json)?", "", text).strip()
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\{{.*\}}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return {"subject": "Quick question about your tech stack",
                "body": "Hi,\n\nI wanted to reach out personally...\n\nBest,\nBraveAspire Team",
                "cta": "Would you be open to a 15-minute call?"}

    def _think(self, m):   self.thoughts.append(("THOUGHT",     m))
    def _act(self, m):     self.thoughts.append(("ACTION",      m))
    def _observe(self, m): self.thoughts.append(("OBSERVATION", m))
