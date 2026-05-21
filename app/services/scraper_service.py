"""
Web scraping service.
  - scrape_company_website(): extract title, description, tech hints from a URL
  - search_companies():       DuckDuckGo HTML search for company discovery
  - hunter_find_emails():     Hunter.io API email finder
  - apollo_enrich():          Apollo.io people enrichment (stub — needs API key)
"""
import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional

logger = logging.getLogger("scraper")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

TECH_KEYWORDS = {
    "React": ["react", "reactjs", "create-react-app"],
    "Vue.js": ["vue", "vuejs", "nuxt"],
    "Angular": ["angular", "angularjs"],
    "Node.js": ["node", "nodejs", "express"],
    "Python": ["python", "django", "flask", "fastapi"],
    "PHP": ["php", "laravel", "symfony", "wordpress"],
    "Java": ["java", "spring", "hibernate"],
    ".NET": ["asp.net", "dotnet", "c#"],
    "AWS": ["aws", "amazon web services", "s3", "ec2", "lambda"],
    "Azure": ["azure", "microsoft cloud"],
    "GCP": ["google cloud", "gcp", "firebase"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Docker": ["docker", "container"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MySQL": ["mysql", "mariadb"],
    "MongoDB": ["mongodb", "mongoose"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic"],
}


# ── Website Scraper ───────────────────────────────────────────────────────────

def scrape_company_website(website: str, timeout: int = 8) -> dict:
    """
    Fetch a company website and extract:
    title, meta description, detected tech stack, about snippet.
    """
    url = website if website.startswith("http") else f"https://{website}"
    result = {"url": url, "title": "", "description": "", "tech_stack": [], "about": ""}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        result["title"] = (soup.title.string or "").strip() if soup.title else ""

        meta_desc = soup.find("meta", {"name": re.compile(r"description", re.I)})
        if meta_desc:
            result["description"] = meta_desc.get("content", "").strip()

        # Detect tech from page source
        page_text = resp.text.lower()
        detected = [tech for tech, kws in TECH_KEYWORDS.items()
                    if any(kw in page_text for kw in kws)]
        result["tech_stack"] = detected

        # About text — first paragraph in main content
        for tag in soup.find_all(["p", "h1", "h2"], limit=15):
            text = tag.get_text(strip=True)
            if len(text) > 60:
                result["about"] = text[:300]
                break

    except requests.RequestException as e:
        result["error"] = str(e)
        logger.warning(f"scrape_company_website failed for {website}: {e}")

    return result


# ── Company Discovery via DuckDuckGo ─────────────────────────────────────────

def search_companies(query: str, max_results: int = 10) -> list[dict]:
    """
    Use DuckDuckGo HTML search (no API key) to find company websites.
    Returns list of {title, url, snippet}.
    """
    results = []
    try:
        search_url = "https://html.duckduckgo.com/html/"
        resp = requests.post(search_url, data={"q": query}, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        for result in soup.select(".result__body")[:max_results]:
            title_tag = result.select_one(".result__title")
            link_tag  = result.select_one(".result__url")
            snip_tag  = result.select_one(".result__snippet")
            if title_tag:
                results.append({
                    "title":   title_tag.get_text(strip=True),
                    "url":     link_tag.get_text(strip=True) if link_tag else "",
                    "snippet": snip_tag.get_text(strip=True) if snip_tag else "",
                })
        time.sleep(1)   # polite delay
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")
    return results


# ── Hunter.io Email Finder ────────────────────────────────────────────────────

def hunter_find_emails(domain: str, api_key: Optional[str] = None) -> list[dict]:
    """
    Use Hunter.io domain search API to find verified emails.
    Returns list of {name, first_name, last_name, email, position, confidence}.
    """
    key = api_key or os.getenv("HUNTER_API_KEY", "")
    if not key:
        return []

    try:
        url = "https://api.hunter.io/v2/domain-search"
        resp = requests.get(url, params={"domain": domain, "api_key": key}, timeout=10)
        data = resp.json()
        if resp.status_code != 200 or "data" not in data:
            return []
        emails = []
        for e in data["data"].get("emails", []):
            emails.append({
                "name":       f"{e.get('first_name','')} {e.get('last_name','')}".strip(),
                "first_name": e.get("first_name", ""),
                "last_name":  e.get("last_name", ""),
                "email":      e.get("value", ""),
                "position":   e.get("position", ""),
                "confidence": e.get("confidence", 0),
                "verified":   e.get("verification", {}).get("status") == "valid",
            })
        return emails
    except Exception as e:
        logger.warning(f"Hunter.io error: {e}")
        return []


# ── Apollo Enrichment (stub) ──────────────────────────────────────────────────

def apollo_enrich_person(first_name: str, last_name: str, domain: str,
                          api_key: Optional[str] = None) -> dict:
    """
    Apollo.io people enrichment — returns email, LinkedIn, phone if found.
    Requires APOLLO_API_KEY.
    """
    key = api_key or os.getenv("APOLLO_API_KEY", "")
    if not key:
        return {"error": "APOLLO_API_KEY not set"}

    try:
        url = "https://api.apollo.io/v1/people/match"
        resp = requests.post(
            url,
            json={"first_name": first_name, "last_name": last_name, "domain": domain},
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache",
                     "X-Api-Key": key},
            timeout=10,
        )
        data = resp.json()
        person = data.get("person", {})
        return {
            "email":    person.get("email", ""),
            "linkedin": person.get("linkedin_url", ""),
            "phone":    person.get("sanitized_phone", ""),
            "title":    person.get("title", ""),
        }
    except Exception as e:
        logger.warning(f"Apollo error: {e}")
        return {"error": str(e)}
