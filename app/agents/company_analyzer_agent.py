import json
import re
from ..services.ai_service import AIService

SYSTEM_PROMPT = """You are a senior business analyst specializing in B2B software sales.
Analyze companies and identify opportunities for software development services.
Always respond with valid JSON only — no markdown, no explanation."""


class CompanyAnalyzerAgent:
    name = "Company Analyzer Agent"

    def __init__(self, ai: AIService):
        self.ai = ai

    def analyze(self, company: dict) -> dict:
        """Deep-analyze a company and return insights dict."""
        prompt = (
            f"Company: {company.get('name')} | Industry: {company.get('industry')} | "
            f"Stack: {company.get('tech_stack')} | Employees: {company.get('employee_size')} | "
            f"Pain: {company.get('pain_points')} | Hiring: {company.get('hiring_status')}\n\n"
            'Return compact JSON: {"score":85,"score_reason":"...","pain_points":["..."],'
            '"services_to_pitch":["..."],"approach_angle":"...","urgency":"High",'
            '"decision_maker_title":"CTO","estimated_deal_size":"$15,000"}'
        )

        raw = self.ai.generate(prompt, system=SYSTEM_PROMPT)
        return self._parse(raw)

    def _parse(self, text: str) -> dict:
        text = re.sub(r"```(?:json)?", "", text).strip()
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return {
            "score": 70,
            "score_reason": "Unable to parse AI response",
            "pain_points": [],
            "services_to_pitch": [],
            "approach_angle": "Generic outreach",
            "urgency": "Medium",
            "decision_maker_title": "CTO",
            "estimated_deal_size": "Unknown",
        }
