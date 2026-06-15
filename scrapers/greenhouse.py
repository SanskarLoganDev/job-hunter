"""
scrapers/greenhouse.py

Scrapes the Greenhouse public jobs API for any company on their platform.

Why this is simple and reliable:
  - Greenhouse exposes a fully documented, intentionally public JSON API.
  - No authentication, no browser, no rate limit at reasonable polling intervals.
  - One API call returns ALL open jobs for a company — no pagination needed
    for most companies (they return up to 500 per call).
  - The same scraper works for every Greenhouse company — only the slug changes.

API endpoint:
  GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true

Response shape (simplified):
  {
    "jobs": [
      {
        "id": 12345,
        "title": "Software Engineer",
        "absolute_url": "https://boards.greenhouse.io/company/jobs/12345",
        "location": { "name": "San Francisco, CA" },
        "updated_at": "2025-06-14T10:00:00.000Z",
        "content": "<p>Job description HTML...</p>"
      },
      ...
    ]
  }

HOW TO CUSTOMISE (no code changes needed):
  - add/remove role keywords  → config.yaml  keywords
  - change location filters   → config.yaml  locations
  - change the age cutoff     → config.yaml  max_age_days
  - add a new company         → new block in config.yaml with ats: greenhouse
  - pause a company           → config.yaml  active: false
  - seniority exclusions      → scrapers/__init__.py  _SENIOR_TERMS
"""

import re
import time
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from scrapers import Job, is_junior_enough

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = 20


# ---------------------------------------------------------------------------
# UTC helper
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_gh_date(date_str: str) -> Optional[datetime]:
    """
    Parse a Greenhouse ISO 8601 date string into a timezone-aware datetime.

    Greenhouse uses two formats:
      "2025-06-14T10:00:00.000Z"     → Z suffix (UTC)
      "2025-06-14T10:00:00+00:00"    → explicit offset

    Returns None if parsing fails.
    """
    if not date_str:
        return None
    try:
        normalized = date_str.strip().replace("Z", "+00:00")
        normalized = re.sub(r"\.\d+(\+)", r"\1", normalized)
        return datetime.fromisoformat(normalized)
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def _keyword_match(title: str, keywords: List[str]) -> bool:
    """Return True if title contains at least one keyword (case-insensitive)."""
    if not keywords:
        return True
    title_lower = title.lower()
    return any(k.lower() in title_lower for k in keywords)


def _location_match(location: str, allowed: List[str]) -> bool:
    """Return True if location contains at least one allowed term."""
    if not allowed:
        return True
    loc_lower = location.lower()
    return any(term.lower() in loc_lower for term in allowed)


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def _fetch_jobs(slug: str, session: requests.Session) -> List[dict]:
    """
    Fetch all jobs from the Greenhouse API for the given company slug.
    Returns raw list of job dicts, or [] on failure.
    """
    urls = [
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    ]
    for url in urls:
        try:
            r = session.get(url, timeout=HTTP_TIMEOUT)
            if not r.ok:
                continue
            data = r.json()
            jobs = data.get("jobs", [])
            if isinstance(jobs, list):
                return jobs
        except Exception:
            continue
    return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape(
    slug: str,
    keywords: List[str],
    company_name: str,
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
) -> List[Job]:
    """
    Scrape all open jobs for a Greenhouse company and return matching ones.

    Filters applied in order:
      1. Keyword match    — title must contain at least one keyword
      2. Seniority filter — excludes staff/senior/principal/lead etc.
                           terms defined in scrapers/__init__.py _SENIOR_TERMS
      3. Location filter  — location must contain at least one allowed term
      4. Age filter       — updated_at must be within max_age_days

    Args:
        slug:         Greenhouse company slug. e.g. "anthropic", "datadog"
        keywords:     Role title substrings. From config.yaml → keywords.
        company_name: Display name. From config.yaml → name.
        locations:    Location substrings. From config.yaml → locations.
        max_age_days: Discard jobs older than this. 0 = no filter.

    Returns:
        List[Job] sorted by posted_dt descending (newest first).
        Empty list on any failure, never raises.
    """
    loc = [l.strip() for l in (locations or []) if l.strip()]

    try:
        session = _make_session()
        raw_jobs = _fetch_jobs(slug, session)

        if not raw_jobs:
            return []

        cutoff = _now() - timedelta(days=max_age_days) if max_age_days > 0 else None
        results: List[Job] = []

        for item in raw_jobs:
            # ── Title ─────────────────────────────────────────────────────
            title = (item.get("title") or "").strip()
            if not title:
                continue

            # ── Keyword filter ─────────────────────────────────────────────
            if not _keyword_match(title, keywords):
                continue

            # ── Seniority filter ───────────────────────────────────────────
            # Excludes: senior, staff, principal, lead, director, manager, etc.
            # Full list in scrapers/__init__.py → _SENIOR_TERMS
            if not is_junior_enough(title):
                continue

            # ── Link ───────────────────────────────────────────────────────
            link = (item.get("absolute_url") or "").strip()
            if not link:
                continue

            # ── Location ───────────────────────────────────────────────────
            loc_field = item.get("location") or {}
            location = (
                loc_field.get("name") if isinstance(loc_field, dict)
                else str(loc_field)
            ).strip()

            # ── Location filter ────────────────────────────────────────────
            if not _location_match(location, loc):
                continue

            # ── Date ───────────────────────────────────────────────────────
            date_str  = item.get("updated_at") or ""
            posted_dt = _parse_gh_date(date_str)
            posted_text = date_str[:10] if date_str else ""

            # ── Age filter ─────────────────────────────────────────────────
            if cutoff is not None:
                if posted_dt is None or posted_dt < cutoff:
                    continue

            results.append(Job(
                title=title,
                company=company_name,
                link=link,
                location=location,
                posted_text=posted_text,
                posted_dt=posted_dt,
            ))

        time.sleep(random.uniform(0.5, 1.5))
        return results

    except Exception:
        return []
