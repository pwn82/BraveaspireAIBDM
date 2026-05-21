import json
import re
from ..services.ai_service import AIService

SYSTEM_PROMPT = """You are an expert B2B lead generation agent.
Your job is to generate realistic, detailed company leads for business development purposes.
Always respond with valid JSON only — no markdown, no explanation."""


class LeadDiscoveryAgent:
    name = "Lead Discovery Agent"

    def __init__(self, ai: AIService):
        self.ai = ai
        self.thoughts: list[tuple[str, str]] = []

    def discover(self, query: str, count: int = 5, filters: dict | None = None) -> tuple[list[dict], list]:
        """
        ReAct loop: Thought → Action → Observation → repeat.
        Returns (companies_list, thought_log).
        """
        self.thoughts = []
        filters = filters or {}

        # Step 1 — THOUGHT
        self._think(f"User wants: '{query}'. Filters: {filters}. Need {count} leads.")

        # Step 2 — ACTION: build prompt
        self._act("Build AI prompt for lead generation")
        prompt = self._build_prompt(query, count, filters)

        # Step 3 — ACTION: call AI
        self._act(f"Calling {self.ai.provider_label} to generate leads")
        raw = self.ai.generate(prompt, system=SYSTEM_PROMPT)

        # Step 4 — OBSERVATION: parse result
        self._observe(f"AI returned {len(raw)} characters")
        companies = self._parse_json_list(raw)

        # Step 5 — THOUGHT: validate
        self._think(f"Parsed {len(companies)} companies. Validating scores and required fields.")
        companies = [self._normalize(c) for c in companies]

        self._observe(f"Returning {len(companies)} validated leads to CRM")
        return companies, self.thoughts

    def _build_prompt(self, query: str, count: int, filters: dict) -> str:
        industry = filters.get("industry", "any industry")
        location = filters.get("location", "worldwide")
        size = filters.get("employee_size", "any size")

        return (
            f"Generate {count} B2B company leads: query={query}, "
            f"industry={industry}, location={location}, size={size}.\n"
            "JSON array only:\n"
            '[{"name":"X","website":"x.com","industry":"SaaS","location":"City, Country",'
            '"employee_size":100,"revenue":"$5M-$10M","score":85,"hiring_status":true,'
            '"tech_stack":"Python,React","pain_points":"needs modernization","source":"AI Discovery"}]'
        )

    def _normalize(self, c: dict) -> dict:
        return {
            "name": str(c.get("name", "Unknown")),
            "website": str(c.get("website", "")),
            "industry": str(c.get("industry", "Technology")),
            "location": str(c.get("location", "USA")),
            "employee_size": int(c.get("employee_size", 100)),
            "revenue": str(c.get("revenue", "Unknown")),
            "score": max(0, min(100, int(c.get("score", 75)))),
            "hiring_status": bool(c.get("hiring_status", False)),
            "tech_stack": str(c.get("tech_stack", "")),
            "pain_points": str(c.get("pain_points", "")),
            "source": "AI Discovery",
            "status": "New",
        }

    def _parse_json_list(self, text: str) -> list:
        text = text.strip()
        # Strip markdown fences if present
        text = re.sub(r"```(?:json)?", "", text).strip()
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return v
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return []

    def _think(self, msg: str):
        self.thoughts.append(("THOUGHT", msg))

    def _act(self, msg: str):
        self.thoughts.append(("ACTION", msg))

    def _observe(self, msg: str):
        self.thoughts.append(("OBSERVATION", msg))
