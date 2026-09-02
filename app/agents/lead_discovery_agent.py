from ..services.ai_service import AIService
from ..schemas.ai_outputs import LeadDiscoveryResult
from ..utils.ai_parsing import parse_ai_json

SYSTEM_PROMPT = """You are a B2B lead discovery analyst.

RULES:
1. Only return companies you have genuine knowledge of — do not invent a
   company, domain, or statistic to fill a quota. If you cannot confidently
   name `count` real companies matching the request, return fewer.
2. Prefer well-known, verifiable companies over obscure guesses.
3. Mark attributes you are not confident about with a low `confidence` value
   rather than guessing a specific number.
4. Never invent contact details — this agent returns companies only, not people.

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
        self._think(f"User wants: '{query}'. Filters: {filters}. Need up to {count} leads.")

        # Step 2 — ACTION: build prompt
        self._act("Build AI prompt for lead generation")
        prompt = self._build_prompt(query, count, filters)

        # Step 3 — ACTION: call AI
        self._act(f"Calling {self.ai.provider_label} to discover leads")
        raw = self.ai.generate(prompt, system=SYSTEM_PROMPT)

        # Step 4 — OBSERVATION: parse + validate result
        self._observe(f"AI returned {len(raw)} characters")
        parsed, err = parse_ai_json(raw, LeadDiscoveryResult)
        if parsed is None:
            self._observe(f"⚠️ AI response could not be validated ({err}) — returning 0 companies "
                          f"rather than fabricated data")
            return [], self.thoughts

        # Step 5 — THOUGHT: validate confidence, drop low-confidence guesses
        self._think(f"AI returned {len(parsed.companies)} companies. Filtering low-confidence entries.")
        companies = [self._normalize(c) for c in parsed.companies if c.confidence >= 0.3]

        self._observe(f"Returning {len(companies)} companies to CRM "
                      f"({len(parsed.companies) - len(companies)} dropped for low confidence)")
        return companies, self.thoughts

    def _build_prompt(self, query: str, count: int, filters: dict) -> str:
        industry = filters.get("industry", "any industry")
        location = filters.get("location", "worldwide")
        size = filters.get("employee_size", "any size")

        return (
            f"Find up to {count} real B2B companies matching: query={query}, "
            f"industry={industry}, location={location}, size={size}.\n"
            'Return JSON: {"companies":[{"name":"X","website":"x.com","industry":"SaaS",'
            '"location":"City, Country","employee_size":100,"revenue":"$5M-$10M",'
            '"score":85,"hiring_status":true,"tech_stack":"Python,React",'
            '"pain_points":"needs modernization","confidence":0.8}]}'
        )

    def _normalize(self, c) -> dict:
        return {
            "name": c.name,
            "website": c.website,
            "industry": c.industry,
            "location": c.location,
            "employee_size": c.employee_size,
            "revenue": c.revenue,
            "score": c.score,
            "hiring_status": c.hiring_status,
            "tech_stack": c.tech_stack,
            "pain_points": c.pain_points,
            "source": "AI Discovery",
            "status": "New",
        }

    def _think(self, msg: str):
        self.thoughts.append(("THOUGHT", msg))

    def _act(self, msg: str):
        self.thoughts.append(("ACTION", msg))

    def _observe(self, msg: str):
        self.thoughts.append(("OBSERVATION", msg))
