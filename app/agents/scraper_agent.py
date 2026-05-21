"""
Scraper Agent — ReAct pattern.
Combines DuckDuckGo search + website scraping + AI analysis
to discover and enrich companies from the public web.
"""
import json
import re
from ..services.ai_service import AIService
from ..services.scraper_service import search_companies, scrape_company_website, hunter_find_emails

SYSTEM = """You are a B2B research agent. Analyze scraped company data and extract structured information.
Always respond with valid JSON only."""


class ScraperAgent:
    name = "Web Scraper Agent"

    def __init__(self, ai: AIService):
        self.ai     = ai
        self.thoughts: list[tuple[str, str]] = []

    def research_company(self, company_name: str, website: str = "") -> dict:
        """
        Full research pipeline for one company.
        Returns enriched company dict.
        """
        self.thoughts = []
        self._think(f"Researching: {company_name}")

        # Step 1 — Scrape website
        if website:
            self._act(f"Scraping website: {website}")
            scraped = scrape_company_website(website)
            self._observe(f"Got title='{scraped.get('title','')}', tech={scraped.get('tech_stack',[])}")
        else:
            scraped = {}

        # Step 2 — Search for more info
        self._act(f"Searching DuckDuckGo for '{company_name}'")
        search_results = search_companies(f"{company_name} software company", max_results=3)
        snippets = " ".join(r.get("snippet", "") for r in search_results)
        self._observe(f"Found {len(search_results)} search results")

        # Step 3 — AI synthesis
        self._act("Calling AI to synthesize research into structured profile")
        prompt = f"""Analyze this scraped data about '{company_name}' and return a structured company profile.

Website title: {scraped.get('title', 'N/A')}
Meta description: {scraped.get('description', 'N/A')}
Detected tech stack: {scraped.get('tech_stack', [])}
About snippet: {scraped.get('about', 'N/A')}
Search snippets: {snippets[:500]}

Return JSON:
{{
  "industry": "...",
  "pain_points": "...",
  "tech_stack": "comma-separated",
  "hiring_status": true/false,
  "score": 1-100,
  "notes": "Key insight for sales approach"
}}"""

        raw    = self.ai.generate(prompt, system=SYSTEM)
        parsed = self._parse_json(raw)
        self._observe(f"AI synthesis complete. Score: {parsed.get('score')}")

        return {
            "name":           company_name,
            "website":        website,
            "industry":       parsed.get("industry", "Technology"),
            "tech_stack":     parsed.get("tech_stack", ", ".join(scraped.get("tech_stack", []))),
            "pain_points":    parsed.get("pain_points", ""),
            "hiring_status":  bool(parsed.get("hiring_status", False)),
            "score":          max(0, min(100, int(parsed.get("score", 70)))),
            "notes":          parsed.get("notes", ""),
            "source":         "Web Scraper",
            "status":         "New",
            "_thoughts":      self.thoughts,
        }

    def discover_from_search(self, query: str, count: int = 5) -> list[dict]:
        """Search + basic profile for N companies matching query."""
        self.thoughts = []
        self._think(f"Discovering companies for: '{query}'")
        self._act(f"Running DuckDuckGo search: '{query} companies'")

        results = search_companies(f"{query} software company", max_results=count * 2)
        self._observe(f"Got {len(results)} raw search results")

        companies = []
        for r in results[:count]:
            title   = r.get("title", "").split("|")[0].strip()
            url     = r.get("url", "")
            snippet = r.get("snippet", "")

            if not title or len(title) < 3:
                continue

            self._act(f"AI-profiling '{title}'")
            prompt = f"""Given this search result about '{title}':
URL: {url}
Snippet: {snippet}

Return a quick company JSON profile:
{{"name": "{title}", "website": "{url}", "industry": "...", "pain_points": "...",
  "employee_size": 100, "score": 70, "hiring_status": false, "source": "Web Search"}}"""

            raw = self.ai.generate(prompt, system=SYSTEM)
            profile = self._parse_json(raw)
            if profile.get("name"):
                profile.setdefault("status", "New")
                companies.append(profile)

        self._observe(f"Returning {len(companies)} discovered companies")
        return companies, self.thoughts

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

    def _think(self, m):  self.thoughts.append(("THOUGHT",      m))
    def _act(self, m):    self.thoughts.append(("ACTION",       m))
    def _observe(self, m):self.thoughts.append(("OBSERVATION",  m))
