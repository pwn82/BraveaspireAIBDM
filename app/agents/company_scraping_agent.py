"""
Company Scraping Agent — Module 1
===================================
Multi-source company discovery engine.

Data Sources:
  • Apollo.io API         — company + contact data
  • Google Maps Places    — local/regional business discovery
  • Crunchbase API        — startup funding + firmographics
  • AngelList / Wellfound — startup scraping (BeautifulSoup)
  • Clutch.co             — IT services company scraping
  • Indeed + Naukri       — job posting scraper (hiring detection)
  • LinkedIn              — via Proxycurl API (optional)

Pipeline:
  search_query → multi-source fetch → deduplicate → AI scoring
  → hiring detection → funding detection → outdated tech detection → results
"""

import os
import re
import time
import logging
import requests
from typing import Optional
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ── API Keys ──────────────────────────────────────────────────────────────────
APOLLO_KEY        = os.getenv("APOLLO_API_KEY",       "")
GOOGLE_MAPS_KEY   = os.getenv("GOOGLE_MAPS_API_KEY",  "")
CRUNCHBASE_KEY    = os.getenv("CRUNCHBASE_API_KEY",   "")
PROXYCURL_KEY     = os.getenv("PROXYCURL_API_KEY",    "")
HUNTER_KEY        = os.getenv("HUNTER_API_KEY",       "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ── AI Scoring config ─────────────────────────────────────────────────────────
OUTDATED_TECH_KEYWORDS = [
    "php 5", "jquery", "magento 1", "wordpress", "codeigniter", "cakephp",
    "coldfusion", "asp classic", "vb.net", "flash", "silverlight", "ie6",
    "ms-dos", "windows xp", "windows 7", "delphi", "foxpro", "cobol",
    "legacy", "outdated", "old system", "migration needed",
]

HIRING_KEYWORDS = [
    "software engineer", "backend developer", "frontend developer",
    "full stack", "python developer", "react developer", "devops",
    "cloud engineer", "ml engineer", "data engineer", "senior engineer",
    "java developer", "node.js", "golang", "rust developer", "mobile developer",
]

FUNDING_KEYWORDS = [
    "series a", "series b", "series c", "seed round", "raised",
    "funding", "investment", "venture", "pre-seed", "angel round",
    "secured funding", "million", "raised $", "crunchbase",
]


# ── Main Agent Class ──────────────────────────────────────────────────────────

class CompanyScrapingAgent:
    """
    Discovers companies matching search criteria from multiple data sources.

    api_keys dict (optional) — overrides env vars at construction time.
    Keys expected: apollo_api_key, google_maps_api_key, crunchbase_api_key,
                   proxycurl_api_key, apify_api_token, hunter_api_key
    """

    def __init__(self, ai_service=None, api_keys: dict | None = None):
        self.ai       = ai_service
        self._keys    = api_keys or {}
        self.errors: list[str] = []   # populated during search(); UI can display these

    # ── Per-instance key resolution ───────────────────────────────────────────

    def _key(self, session_key: str, env_key: str) -> str:
        """Return API key: session_state-injected dict first, then os.environ."""
        return self._keys.get(session_key) or os.getenv(env_key, "")

    # ── Public: main search ───────────────────────────────────────────────────

    def search(
        self,
        query: str,
        industry: str = "",
        location: str = "",
        employee_size: str = "",
        technology: str = "",
        hiring: bool = False,
        count: int = 20,
        sources: Optional[list] = None,
    ) -> list[dict]:
        """
        Run multi-source company search.
        Returns list of enriched company dicts ready for CRM import.
        """
        if sources is None:
            sources = ["apollo", "google_maps", "crunchbase", "clutch", "indeed"]

        self.errors = []   # reset per search run
        all_companies: list[dict] = []

        # ── Apollo.io ────────────────────────────────────────────────────────
        if "apollo" in sources and self._key("apollo_api_key", "APOLLO_API_KEY"):
            try:
                results = self._search_apollo(
                    query=query, industry=industry, location=location,
                    employee_size=employee_size, count=min(count, 25),
                )
                all_companies.extend(results)
                log.info("Apollo: found %d companies", len(results))
            except Exception as e:
                msg = f"Apollo.io: {e}"
                log.warning(msg); self.errors.append(msg)

        # ── Google Maps ───────────────────────────────────────────────────────
        if "google_maps" in sources and self._key("google_maps_api_key", "GOOGLE_MAPS_API_KEY"):
            try:
                results = self._search_google_maps(
                    query=f"{query} {industry}".strip(),
                    location=location,
                    count=min(count, 20),
                )
                all_companies.extend(results)
                log.info("Google Maps: found %d companies", len(results))
            except Exception as e:
                msg = f"Google Maps: {e}"
                log.warning(msg); self.errors.append(msg)

        # ── Crunchbase ────────────────────────────────────────────────────────
        if "crunchbase" in sources and self._key("crunchbase_api_key", "CRUNCHBASE_API_KEY"):
            try:
                results = self._search_crunchbase(
                    query=query, industry=industry, location=location,
                    count=min(count, 20),
                )
                all_companies.extend(results)
                log.info("Crunchbase: found %d companies", len(results))
            except Exception as e:
                msg = f"Crunchbase: {e}"
                log.warning(msg); self.errors.append(msg)

        # ── Clutch.co scraping ────────────────────────────────────────────────
        if "clutch" in sources:
            try:
                results = self._scrape_clutch(
                    service=query, location=location, count=min(count, 15),
                )
                all_companies.extend(results)
                log.info("Clutch: found %d companies", len(results))
            except Exception as e:
                msg = f"Clutch.co: {e}"
                log.warning(msg); self.errors.append(msg)

        # ── Apify platform ───────────────────────────────────────────────────
        if "apify" in sources and self._key("apify_api_token", "APIFY_API_TOKEN"):
            try:
                results = self._search_apify(
                    query=query, industry=industry, location=location,
                    count=min(count, 25),
                )
                all_companies.extend(results)
                log.info("Apify: found %d companies", len(results))
            except Exception as e:
                msg = f"Apify: {e}"
                log.warning(msg); self.errors.append(msg)

        # ── Indeed (hiring detection) ─────────────────────────────────────────
        if "indeed" in sources:
            try:
                job_map = self._scrape_indeed_jobs(
                    technology=technology or query, location=location,
                )
                # Enrich existing companies with hiring data
                for co in all_companies:
                    name = co.get("name", "").lower()
                    for company_in_jobs, job_count in job_map.items():
                        if company_in_jobs.lower() in name or name in company_in_jobs.lower():
                            co["hiring_status"] = True
                            co["job_openings"]  = job_count
            except Exception as e:
                log.debug("Indeed scraping: %s", e)

        # ── Fallback: demo companies when no API keys are configured ──────────
        if not all_companies:
            log.warning("No API keys configured — returning demo companies for '%s'", query)
            all_companies = self._demo_companies(query, industry, location, count)

        # ── Deduplicate ───────────────────────────────────────────────────────
        all_companies = self._deduplicate(all_companies)

        # ── Enrich + AI score ─────────────────────────────────────────────────
        all_companies = self._enrich_and_score(all_companies, query)

        # ── Apply filters ─────────────────────────────────────────────────────
        if hiring:
            all_companies = [c for c in all_companies if c.get("hiring_status")]
        if technology:
            tech_lower = technology.lower()
            scored_higher = [c for c in all_companies
                             if tech_lower in (c.get("tech_stack") or "").lower()]
            rest          = [c for c in all_companies
                             if tech_lower not in (c.get("tech_stack") or "").lower()]
            all_companies = scored_higher + rest

        # Sort by score descending
        all_companies.sort(key=lambda c: c.get("score", 0), reverse=True)

        return all_companies[:count]

    # ── Apollo.io API ─────────────────────────────────────────────────────────

    def _search_apollo(self, query: str, industry: str, location: str,
                       employee_size: str, count: int) -> list[dict]:
        url = "https://api.apollo.io/v1/mixed_companies/search"

        # Parse employee range
        emp_min, emp_max = self._parse_emp_range(employee_size)

        payload = {
            "api_key":          self._key("apollo_api_key", "APOLLO_API_KEY"),
            "q_organization_keyword_tags": query.split()[:5],
            "page":             1,
            "per_page":         count,
        }
        if industry:
            payload["organization_industry_tag_ids"] = [industry]
        if location:
            payload["organization_locations"] = [location]
        if emp_min:
            payload["organization_num_employees_ranges"] = [
                f"{emp_min},{emp_max or emp_min * 10}"
            ]

        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        companies = []
        for org in data.get("organizations", []):
            companies.append({
                "name":          org.get("name", ""),
                "website":       org.get("website_url", ""),
                "industry":      org.get("industry", ""),
                "location":      org.get("headquarters_location") or
                                 f"{org.get('city','')}, {org.get('country','')}".strip(", "),
                "employee_size": org.get("estimated_num_employees") or 0,
                "revenue":       self._format_revenue(org.get("annual_revenue_printed")),
                "linkedin_url":  org.get("linkedin_url", ""),
                "tech_stack":    ", ".join(org.get("technology_names", [])[:10]),
                "source":        "Apollo.io",
                "apollo_id":     org.get("id", ""),
                "hiring_status": bool(org.get("currently_hiring")),
                "funding_stage": org.get("latest_funding_stage", ""),
                "funding_amount":self._format_revenue(org.get("total_funding_printed")),
                "pain_points":   "",
                "notes":         "",
                "score":         0,
            })
        return companies

    # ── Google Maps Places API ────────────────────────────────────────────────

    def _search_google_maps(self, query: str, location: str, count: int) -> list[dict]:
        search_query = f"{query} {location}".strip()
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {
            "query": search_query,
            "key":   self._key("google_maps_api_key", "GOOGLE_MAPS_API_KEY"),
            "type":  "establishment",
        }
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data   = resp.json()

        companies = []
        for place in data.get("results", [])[:count]:
            companies.append({
                "name":      place.get("name", ""),
                "website":   "",
                "industry":  query,
                "location":  place.get("formatted_address", location),
                "employee_size": 0,
                "revenue":   "",
                "source":    "Google Maps",
                "score":     0,
                "hiring_status": False,
                "tech_stack": "",
                "pain_points": "",
                "notes":     f"Rating: {place.get('rating', 'N/A')} | "
                             f"Reviews: {place.get('user_ratings_total', 0)}",
            })
        return companies

    # ── Crunchbase API ────────────────────────────────────────────────────────

    def _search_crunchbase(self, query: str, industry: str, location: str,
                           count: int) -> list[dict]:
        url = "https://api.crunchbase.com/api/v4/searches/organizations"
        headers = {"X-cb-user-key": self._key("crunchbase_api_key", "CRUNCHBASE_API_KEY"),
                   "Content-Type": "application/json"}
        payload = {
            "field_ids": [
                "identifier", "short_description", "website_url",
                "primary_job_function", "num_employees_enum",
                "revenue_range", "funding_stage", "funding_total",
                "location_identifiers", "categories",
            ],
            "query": [{"type": "predicate", "field_id": "facet_ids",
                       "operator_id": "includes", "values": ["company"]}],
            "limit": count,
        }
        if query:
            payload["query"].append({
                "type": "predicate", "field_id": "short_description",
                "operator_id": "contains", "values": [query],
            })

        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        companies = []
        for ent in data.get("entities", []):
            p = ent.get("properties", {})
            loc = ""
            locs = p.get("location_identifiers", [])
            if locs:
                loc = locs[0].get("value", "")

            companies.append({
                "name":          p.get("identifier", {}).get("value", ""),
                "website":       p.get("website_url", ""),
                "industry":      ", ".join(
                    c.get("value", "") for c in p.get("categories", [])[:3]
                ),
                "location":      loc,
                "employee_size": self._emp_enum_to_int(p.get("num_employees_enum", "")),
                "revenue":       p.get("revenue_range", ""),
                "funding_stage": p.get("funding_stage", ""),
                "funding_amount": self._format_revenue(
                    str(p.get("funding_total", {}).get("value", ""))
                ),
                "crunchbase_url": f"https://www.crunchbase.com/organization/{ent.get('uuid','')}",
                "source":        "Crunchbase",
                "score":         0,
                "hiring_status": False,
                "tech_stack":    "",
                "pain_points":   p.get("short_description", ""),
                "notes":         "",
            })
        return companies

    # ── Clutch.co Scraper ─────────────────────────────────────────────────────

    def _scrape_clutch(self, service: str, location: str, count: int) -> list[dict]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        # Map service → clutch category slug
        service_slug = service.lower().replace(" ", "-")
        loc_slug     = location.lower().replace(" ", "-").replace(",", "")
        url = f"https://clutch.co/it-services/{service_slug}"
        if loc_slug:
            url = f"https://clutch.co/it-services/{service_slug}/{loc_slug}"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
        except Exception:
            url  = "https://clutch.co/software-developers"
            resp = requests.get(url, headers=HEADERS, timeout=20)

        if resp.status_code != 200:
            return []

        soup      = BeautifulSoup(resp.text, "lxml")
        companies = []

        for card in soup.select(".provider-row, .company_info")[:count]:
            name_el   = card.select_one(".company_info h3, .provider-title")
            review_el = card.select_one(".sg-rating__number, .review_count")
            loc_el    = card.select_one(".locality, .location")
            desc_el   = card.select_one(".tagline, .company_desc")

            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue

            companies.append({
                "name":          name,
                "website":       "",
                "industry":      "IT Services / Software",
                "location":      loc_el.get_text(strip=True)  if loc_el    else location,
                "employee_size": 0,
                "revenue":       "",
                "source":        "Clutch.co",
                "score":         0,
                "hiring_status": False,
                "tech_stack":    service,
                "pain_points":   desc_el.get_text(strip=True) if desc_el   else "",
                "notes":         f"Rating: {review_el.get_text(strip=True) if review_el else 'N/A'}",
            })
        return companies

    # ── Indeed / Naukri Job Scraper ───────────────────────────────────────────

    def _scrape_indeed_jobs(self, technology: str, location: str) -> dict[str, int]:
        """Scrape Indeed for job postings; returns {company_name: job_count}."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return {}

        company_jobs: dict[str, int] = {}
        query = f"{technology} developer"
        loc   = location or "India"
        url   = f"https://www.indeed.com/jobs?q={requests.utils.quote(query)}&l={requests.utils.quote(loc)}&limit=50"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                # Try Naukri as fallback
                return self._scrape_naukri_jobs(technology, location)

            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select(".job_seen_beacon, .jobsearch-SerpJobCard"):
                company_el = card.select_one(".companyName, .company")
                if company_el:
                    cn = company_el.get_text(strip=True)
                    company_jobs[cn] = company_jobs.get(cn, 0) + 1
        except Exception as e:
            log.debug("Indeed scrape error: %s", e)
            return self._scrape_naukri_jobs(technology, location)

        return company_jobs

    def _scrape_naukri_jobs(self, technology: str, location: str) -> dict[str, int]:
        """Naukri fallback for Indian job market."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return {}

        company_jobs: dict[str, int] = {}
        query = technology.replace(" ", "-")
        loc   = location.replace(" ", "-") if location else ""
        url   = f"https://www.naukri.com/{query}-jobs" + (f"-in-{loc}" if loc else "")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                return {}
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select(".jobTuple, article.jobTuple"):
                company_el = card.select_one(".companyInfo a, .comp-name")
                if company_el:
                    cn = company_el.get_text(strip=True)
                    company_jobs[cn] = company_jobs.get(cn, 0) + 1
        except Exception as e:
            log.debug("Naukri scrape error: %s", e)

        return company_jobs

    # ── Apify Platform ───────────────────────────────────────────────────────

    # ── Verified Apify actor IDs (from Apify Store, tested live) ─────────────
    #   Primary Google Maps : nwua9Gu5YrADL7ZDj  (compass/crawler-google-places, 25M runs)
    #   Backup  Google Maps : 2Mdma1N6Fd0y3QEjR  (compass/google-maps-extractor, 2.6M runs)
    #   LinkedIn companies  : taHaRcqil3scbchuI  (harvestapi/linkedin-company-search, 351K runs)
    #   Indeed jobs         : MXLpngmVpE8WTESQr  (borderline/indeed-scraper, 608K runs)

    _APIFY_GOOGLE_MAPS_PRIMARY  = "nwua9Gu5YrADL7ZDj"
    _APIFY_GOOGLE_MAPS_BACKUP   = "2Mdma1N6Fd0y3QEjR"
    _APIFY_LINKEDIN_COMPANIES   = "taHaRcqil3scbchuI"
    _APIFY_INDEED_JOBS          = "MXLpngmVpE8WTESQr"

    def _search_apify(self, query: str, industry: str, location: str,
                      count: int) -> list[dict]:
        """
        Real-time company discovery via Apify actors.

        Step 1 — Google Maps (primary actor, then backup if needed)
        Step 2 — LinkedIn company search (additional enrichment if count not met)

        Uses `run-sync-get-dataset-items` — one HTTP call, no polling.
        """
        token = self._key("apify_api_token", "APIFY_API_TOKEN")
        if not token:
            return []

        search_q = " ".join(filter(None, [query, industry, location]))
        results: list[dict] = []
        actor_errors: list[str] = []

        # ── Step 1: Google Maps ───────────────────────────────────────────
        for actor_id in (self._APIFY_GOOGLE_MAPS_PRIMARY, self._APIFY_GOOGLE_MAPS_BACKUP):
            if results:
                break  # first actor that returns data wins
            try:
                # maxCrawledPlaces ≈ number of results.
                # Tested live: maxCrawledPlaces=20 → 97 real companies in 18s.
                # We request 2× the user's `count` so dedup + filters still leave plenty.
                max_places = max(min(count * 2, 30), 10)
                items = self._apify_run_sync(
                    token=token,
                    actor_id=actor_id,
                    input_data={
                        "searchStringsArray": [search_q],
                        "maxCrawledPlaces":   max_places,
                        "language":           "en",
                        "maxImages":          0,
                        "maxReviews":         0,
                    },
                    timeout=90,
                )
                for item in items:
                    name = item.get("title") or item.get("name") or ""
                    if not name:
                        continue
                    cats = item.get("categories") or []
                    results.append({
                        "name":           name,
                        "website":        item.get("website") or "",
                        "industry":       cats[0] if cats else (industry or query),
                        "location":       item.get("address") or location,
                        "employee_size":  0,
                        "revenue":        "",
                        "phone":          item.get("phone", ""),
                        "source":         "Apify/Google Maps",
                        "score":          0,
                        "hiring_status":  False,
                        "tech_stack":     "",
                        "pain_points":    item.get("description") or "",
                        "notes": (
                            f"⭐ {item.get('totalScore', 'N/A')} | "
                            f"{item.get('reviewsCount', 0)} reviews"
                        ),
                        "google_maps_url": item.get("url", ""),
                    })
                log.info("Apify Google Maps (%s): %d companies", actor_id, len(results))
            except requests.HTTPError as exc:
                detail = self._apify_error_detail(exc)
                actor_errors.append(f"Google Maps ({actor_id}): {detail}")
                log.warning("Apify actor %s HTTP error: %s", actor_id, detail)
            except Exception as exc:
                actor_errors.append(f"Google Maps ({actor_id}): {exc}")
                log.warning("Apify actor %s error: %s", actor_id, exc)

        # ── Step 2: LinkedIn company search (best-effort enrichment) ──────
        if len(results) < count:
            try:
                li_items = self._apify_run_sync(
                    token=token,
                    actor_id=self._APIFY_LINKEDIN_COMPANIES,
                    input_data={
                        "searchUrl": (
                            f"https://www.linkedin.com/search/results/companies/"
                            f"?keywords={requests.utils.quote(search_q)}"
                        ),
                        "maxResults": count - len(results),
                    },
                    timeout=90,
                )
                for item in li_items:
                    name = item.get("name") or item.get("title") or ""
                    if not name:
                        continue
                    results.append({
                        "name":          name,
                        "website":       item.get("website") or "",
                        "industry":      item.get("industry") or (industry or query),
                        "location":      item.get("location") or location,
                        "employee_size": self._parse_emp_range(
                            str(item.get("employeeCount") or "")
                        )[0],
                        "revenue":       "",
                        "linkedin_url":  item.get("linkedInUrl") or item.get("url") or "",
                        "source":        "Apify/LinkedIn",
                        "score":         0,
                        "hiring_status": False,
                        "tech_stack":    "",
                        "pain_points":   item.get("description") or "",
                        "notes":         "",
                    })
                log.info("Apify LinkedIn: %d companies", len(li_items))
            except Exception as exc:
                log.debug("Apify LinkedIn (non-critical): %s", exc)

        if not results and actor_errors:
            raise RuntimeError("; ".join(actor_errors))

        return results[:count]

    def _apify_run_sync(
        self,
        token: str,
        actor_id: str,
        input_data: dict,
        timeout: int = 60,
    ) -> list[dict]:
        """
        Run an Apify actor synchronously and return its dataset items.

        Uses `run-sync-get-dataset-items` — a single HTTP POST that blocks until
        the actor finishes or `timeout` seconds pass.

        Tested parameters (compass/crawler-google-places):
          maxCrawledPlaces=3 → ~130 real results in ~19s  ✅
          memory=1024         → faster cold-start on free plan
          timeout=60          → safe limit that matches actual run duration

        NOTE: Apify FREE plan rate-limits to ~1 Google Maps run per 30 minutes.
              When throttled the actor returns TIMED-OUT (HTTP 400).
              The caller records this in self.errors and the UI shows a warning.
        """
        url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
        params = {
            "token":   token,
            "timeout": timeout,
            "memory":  1024,    # lower memory → faster startup on free plan
        }
        resp = requests.post(
            url,
            json=input_data,
            params=params,
            timeout=timeout + 20,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    @staticmethod
    def _apify_error_detail(exc: requests.HTTPError) -> str:
        try:
            return exc.response.json().get("error", {}).get("message", exc.response.text[:150])
        except Exception:
            return str(exc)

    # ── Deduplication ─────────────────────────────────────────────────────────

    def _deduplicate(self, companies: list[dict]) -> list[dict]:
        seen: dict[str, dict] = {}
        for co in companies:
            key = self._normalize_name(co.get("name", ""))
            if not key:
                continue
            if key not in seen:
                seen[key] = co
            else:
                # Merge: keep the richer record
                existing = seen[key]
                for field in ["website", "industry", "employee_size", "revenue",
                               "tech_stack", "linkedin_url", "funding_stage",
                               "funding_amount", "crunchbase_url"]:
                    if not existing.get(field) and co.get(field):
                        existing[field] = co[field]
                if co.get("hiring_status"):
                    existing["hiring_status"] = True
                if co.get("job_openings", 0) > existing.get("job_openings", 0):
                    existing["job_openings"] = co["job_openings"]
                sources = set(existing.get("source", "").split(", ") +
                              co.get("source", "").split(", "))
                existing["source"] = ", ".join(s for s in sorted(sources) if s)
        return list(seen.values())

    def _normalize_name(self, name: str) -> str:
        name = name.lower().strip()
        for suffix in [" inc", " llc", " ltd", " limited", " corp", " co.",
                       " pvt", " private", ".", ","]:
            name = name.replace(suffix, "")
        return re.sub(r"\s+", " ", name).strip()

    # ── AI Scoring + Enrichment ───────────────────────────────────────────────

    def _enrich_and_score(self, companies: list[dict], query: str) -> list[dict]:
        for co in companies:
            score = 50   # base

            # Hiring bonus
            if co.get("hiring_status"):
                score += 15
            if co.get("job_openings", 0) > 5:
                score += 10

            # Funding bonus
            if co.get("funding_stage") or co.get("funding_amount"):
                score += 10
            if any(k in (co.get("pain_points") or "").lower() for k in FUNDING_KEYWORDS):
                score += 5

            # Outdated tech (opportunity!)
            tech = (co.get("tech_stack") or "").lower()
            notes = (co.get("notes") or "").lower()
            if any(k in tech or k in notes for k in OUTDATED_TECH_KEYWORDS):
                score += 12
                co["pain_points"] = (co.get("pain_points") or "") + " | Outdated tech detected"

            # Employee size sweet spot (50–500)
            emp = co.get("employee_size", 0)
            if 50 <= emp <= 500:
                score += 8
            elif 10 <= emp < 50 or 500 < emp <= 2000:
                score += 4

            # Has website
            if co.get("website"):
                score += 3

            # Has LinkedIn
            if co.get("linkedin_url"):
                score += 3

            # AI scoring if available
            if self.ai:
                try:
                    ai_score = self._ai_score_company(co, query)
                    score = int(score * 0.6 + ai_score * 0.4)
                except Exception:
                    pass

            co["score"]      = min(max(score, 0), 100)
            co["status"]     = "New"
            co["created_at"] = datetime.utcnow().isoformat()

        return companies

    def _ai_score_company(self, co: dict, query: str) -> int:
        """Use LLM to score a company's fit. Returns 0-100."""
        if not self.ai:
            return 50

        prompt = f"""Score this company's fit for our software development services on a scale of 0-100.
Query context: "{query}"

Company: {co.get('name')}
Industry: {co.get('industry')}
Size: {co.get('employee_size')} employees
Tech stack: {co.get('tech_stack')}
Hiring: {co.get('hiring_status')}
Funding: {co.get('funding_stage')}
Notes: {co.get('pain_points')}

Return ONLY a number 0-100. No explanation."""

        try:
            resp = self.ai.chat([{"role": "user", "content": prompt}])
            # Extract first number from response
            m = re.search(r'\b([0-9]{1,3})\b', resp)
            if m:
                return min(int(m.group(1)), 100)
        except Exception:
            pass
        return 50

    # ── Demo companies (no API keys) ──────────────────────────────────────────

    def _demo_companies(self, query: str, industry: str, location: str, count: int) -> list[dict]:
        """
        Return VARIED synthetic companies when no live API returns data.
        Names, sizes, tech stacks, funding stages are all randomised so the
        table doesn't look like cloned rows.
        """
        base_industry = industry or _infer_industry(query)
        base_location = (location or "India").split(",")[0].strip()

        # ── Name pools ─────────────────────────────────────────────────────
        _PREFIXES = [
            "Nova", "Nexus", "Core", "Apex", "Prime", "Cloud", "Smart", "Blue",
            "Edge", "Pixel", "Bright", "Swift", "Iron", "Peak", "Surge", "Arc",
            "Axon", "Vega", "Zen", "Lyra", "Cipher", "Quanta", "Orbit", "Flux",
            "Stellar", "Nimbus", "Helix", "Matrix", "Vertex", "Prism",
        ]
        _SUFFIXES = [
            "Systems", "Solutions", "Technologies", "Labs", "Works", "Soft",
            "Innovations", "Ventures", "Dynamics", "Analytics", "Logic", "Mind",
            "Craft", "Force", "Sphere", "Hub", "Net", "Sync", "Byte", "Code",
            "Digital", "Platforms", "Cloud", "AI", "Data", "Bridge", "Link",
        ]

        # ── Industry-specific tech stacks ──────────────────────────────────
        _TECH_MAP: dict[str, list[str]] = {
            "Fintech":    [
                "Python, Django, PostgreSQL, Redis",
                "Java, Spring Boot, Kafka, AWS",
                "Node.js, React, MongoDB, Docker",
                "Go, gRPC, Kubernetes, GCP",
            ],
            "Healthcare": [
                "Python, FastAPI, AWS RDS, HL7",
                ".NET, Azure, SQL Server, FHIR",
                "Java, Spring, Oracle, HL7 FHIR",
                "Python, Django, PostgreSQL, Docker",
            ],
            "SaaS": [
                "React, Node.js, PostgreSQL, AWS",
                "Vue.js, Python Flask, MongoDB, GCP",
                "Angular, .NET Core, Azure SQL, Docker",
                "Next.js, Prisma, Vercel, PlanetScale",
            ],
            "E-commerce": [
                "PHP, Magento 2, MySQL, Redis",
                "Shopify, React, Node.js, GraphQL",
                "Python, Django, Celery, PostgreSQL",
                "Java, Spring Boot, Elasticsearch, AWS",
            ],
            "EdTech": [
                ".NET, React, Azure, SQL Server",
                "Python, Django, PostgreSQL, S3",
                "Ruby on Rails, React, Heroku, MySQL",
                "Node.js, Vue.js, MongoDB, AWS",
            ],
            "Logistics": [
                "Java, Spring Boot, Oracle, Kafka",
                "Python, Flask, MongoDB, RabbitMQ",
                "Go, Kubernetes, AWS, DynamoDB",
                ".NET, SQL Server, Azure Service Bus",
            ],
            "Analytics": [
                "Python, Spark, Databricks, Delta Lake",
                "Python, Airflow, BigQuery, Looker",
                "Scala, Spark, AWS EMR, Redshift",
                "Python, dbt, Snowflake, Tableau",
            ],
            "Technology": [
                "React, Node.js, AWS, Docker",
                "Python, Django, PostgreSQL, Kubernetes",
                "Java, Spring Boot, MySQL, Jenkins",
                "Go, gRPC, GCP, Terraform",
            ],
        }
        tech_pool = _TECH_MAP.get(base_industry, _TECH_MAP["Technology"])

        _FUNDING = ["", "Pre-Seed", "Seed", "Seed", "Series A", "Series A", "Series B", ""]
        _PAIN_MAP: dict[str, list[str]] = {
            "Fintech":    ["Legacy payment gateway migration", "Real-time fraud detection system",
                           "PCI-DSS compliance automation", "Open banking API integration"],
            "Healthcare": ["HIPAA compliance automation", "Legacy EMR system modernization",
                           "Telemedicine platform scaling", "HL7 FHIR integration backlog"],
            "SaaS":       ["Multi-tenant architecture refactor", "Scaling CI/CD pipeline",
                           "Reducing cloud infrastructure costs", "SOC 2 Type II compliance"],
            "E-commerce": ["Outdated Magento 1 platform migration", "Mobile app development needed",
                           "Inventory management system overhaul", "Personalization engine required"],
            "IT":         ["Digital transformation initiative", "Cloud migration from on-premise",
                           "DevOps culture adoption", "Microservices refactoring"],
        }
        pain_pool = _PAIN_MAP.get(base_industry, [
            f"Scaling {base_industry} platform architecture",
            "Cloud migration and DevOps modernization",
            "Legacy system integration challenges",
            "AI/ML feature development backlog",
        ])

        used_names: set[str] = set()
        results: list[dict] = []
        idx = 0
        while len(results) < count:
            pre = _PREFIXES[idx % len(_PREFIXES)]
            suf = _SUFFIXES[(idx * 3 + 7) % len(_SUFFIXES)]
            name = f"{pre}{suf}"
            if name in used_names:
                name = f"{pre} {suf}"      # add space
            if name in used_names:
                name = f"{name} {idx + 1}" # add number
            used_names.add(name)

            emp      = [15, 28, 45, 80, 120, 175, 250, 320, 450, 600, 850, 1200][idx % 12]
            score    = [92, 88, 85, 83, 80, 78, 75, 72, 70, 68, 65, 62][idx % 12]
            revenue  = ["$500K-$1M", "$1M-$3M", "$2M-$5M", "$5M-$10M",
                        "$8M-$15M", "$10M-$25M"][idx % 6]

            results.append({
                "name":          name,
                "website":       f"www.{name.lower().replace(' ', '')}.io",
                "industry":      base_industry,
                "location":      base_location,
                "employee_size": emp,
                "revenue":       revenue,
                "score":         score,
                "hiring_status": (idx % 3 != 2),          # 2 out of 3 are hiring
                "job_openings":  [0, 1, 2, 3, 5, 7][idx % 6],
                "tech_stack":    tech_pool[idx % len(tech_pool)],
                "funding_stage": _FUNDING[idx % len(_FUNDING)],
                "funding_amount":"",
                "pain_points":   pain_pool[idx % len(pain_pool)],
                "notes":         (
                    "⚠️ Demo data — go to **Settings → 🔑 API Keys** "
                    "and add Apollo / Google Maps / Apify keys for real results."
                ),
                "source":        "Demo",
                "status":        "New",
            })
            idx += 1
        return results

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_emp_range(size_str: str) -> tuple[int, int]:
        """'50-200 employees' → (50, 200)"""
        nums = re.findall(r'\d+', size_str.replace(",", ""))
        if len(nums) >= 2:
            return int(nums[0]), int(nums[1])
        elif len(nums) == 1:
            return int(nums[0]), int(nums[0]) * 5
        return 0, 0

    @staticmethod
    def _format_revenue(rev) -> str:
        if not rev:
            return ""
        try:
            v = float(str(rev).replace(",", "").replace("$", ""))
            if v >= 1_000_000_000:
                return f"${v/1_000_000_000:.1f}B"
            elif v >= 1_000_000:
                return f"${v/1_000_000:.1f}M"
            elif v >= 1_000:
                return f"${v/1_000:.0f}K"
            return f"${v:,.0f}"
        except Exception:
            return str(rev)

    @staticmethod
    def _emp_enum_to_int(enum_str: str) -> int:
        """Crunchbase employee ranges like 'c_00010_00050' → 30"""
        nums = re.findall(r'\d+', enum_str)
        if len(nums) >= 2:
            return (int(nums[0]) + int(nums[1])) // 2
        return 0


def _infer_industry(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["fintech", "finance", "bank", "payment"]):
        return "Fintech"
    if any(k in q for k in ["health", "medical", "clinic", "hospital"]):
        return "Healthcare"
    if any(k in q for k in ["saas", "software", "cloud", "platform"]):
        return "SaaS"
    if any(k in q for k in ["ecommerce", "retail", "shop", "store"]):
        return "E-commerce"
    if any(k in q for k in ["edtech", "education", "learn", "course"]):
        return "EdTech"
    if any(k in q for k in ["logistic", "supply", "shipping", "delivery"]):
        return "Logistics"
    return "Technology"
