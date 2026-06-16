"""
scrapers/lever.py

Scrapes the Lever public Postings API for any company on their platform.

API reference: https://github.com/lever/postings-api
Official docs:  https://developers.lever.co/postings

Why the public v0 API (not v1):
  - v0 requires NO authentication — designed for public job boards.
  - v1 requires an employer API key — employer-side only.
  - v0 returns all published postings with title, location, categories,
    hostedUrl, applyUrl, and createdAt timestamp.

API endpoint:
  GET https://api.lever.co/v0/postings/{slug}?mode=json&limit=500

Response shape (simplified):
  [
    {
      "id": "abc-123-def",
      "text": "Software Engineer",           ← job title
      "categories": {
        "location": "San Francisco, CA",
        "team":     "Engineering",
        "department": "Platform"
      },
      "hostedUrl":  "https://jobs.lever.co/company/abc-123-def",
      "applyUrl":   "https://jobs.lever.co/company/abc-123-def/apply",
      "createdAt":  1718035200000,            ← Unix timestamp in milliseconds
    }
  ]

NOTE on dates:
  Lever's createdAt is a Unix timestamp in MILLISECONDS (not seconds).
  Divide by 1000 before passing to datetime.fromtimestamp().
  This is the posting creation date — accurate for freshness filtering.

HOW TO CUSTOMISE (no code changes needed):
  - add/remove role keywords  → config/config-lever.yaml  keywords
  - change location filters   → config/config-lever.yaml  locations
  - change the age cutoff     → config/config-lever.yaml  max_age_days
  - add a new company         → new block in config/config-lever.yaml
  - pause a company           → config/config-lever.yaml  active: false
  - seniority exclusions      → scrapers/__init__.py  _SENIOR_TERMS
"""

import random
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from scrapers import Job, is_junior_enough

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_BASE     = "https://api.lever.co/v0/postings/{slug}?mode=json&limit=500"
HTTP_TIMEOUT = 20


# ---------------------------------------------------------------------------
# UTC helper
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_lever_date(created_at) -> Optional[datetime]:
    """
    Parse Lever's createdAt field into a timezone-aware UTC datetime.

    Lever returns Unix timestamps in MILLISECONDS as an integer.
    e.g. 1718035200000 → 2024-06-10T16:00:00+00:00

    Returns None if parsing fails.
    """
    if created_at is None:
        return None
    try:
        ts_ms = int(created_at)
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
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
    Fetch all published jobs from the Lever public v0 API.

    No authentication required. Returns raw list of posting dicts or [].

    Lever returns a JSON array (not wrapped in an object like Greenhouse/Ashby).
    """
    url = API_BASE.format(slug=slug)
    try:
        r = session.get(url, timeout=HTTP_TIMEOUT)
        if not r.ok:
            return []
        data = r.json()
        # Lever returns a plain JSON array
        return data if isinstance(data, list) else []
    except Exception:
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
    Scrape all published jobs for a Lever company and return matching ones.

    Filters applied in order:
      1. Keyword match    — title must contain at least one keyword
      2. Seniority filter — excludes staff/senior/principal/lead/director/manager
      3. Location filter  — location must contain at least one allowed term
      4. Age filter       — createdAt must be within max_age_days

    Args:
        slug:         Lever company slug from the URL. e.g. "netlify", "plaid"
                      From config/config-lever.yaml → slug.
        keywords:     Role title substrings. From config → keywords.
        company_name: Display name. From config → name.
        locations:    Location substrings. From config → locations.
        max_age_days: Discard jobs older than this. 0 = no filter.

    Returns:
        List[Job] — empty on any failure, never raises.
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
            # Lever uses "text" for the job title
            title = (item.get("text") or "").strip()
            if not title:
                continue

            # ── Keyword filter ─────────────────────────────────────────────
            if not _keyword_match(title, keywords):
                continue

            # ── Seniority filter ───────────────────────────────────────────
            if not is_junior_enough(title):
                continue

            # ── Link ───────────────────────────────────────────────────────
            # Prefer hostedUrl (listing page) over applyUrl (form)
            link = (item.get("hostedUrl") or item.get("applyUrl") or "").strip()
            if not link:
                continue

            # ── Location ───────────────────────────────────────────────────
            # Lever nests location inside categories: {"location": "San Francisco, CA"}
            categories = item.get("categories") or {}
            location = (categories.get("location") or "").strip()

            # Some Lever postings also have workplaceType at top level
            workplace = (item.get("workplaceType") or "").strip().lower()
            if workplace in ("remote", "hybrid") and "remote" not in location.lower():
                location = f"{location}; Remote".strip("; ")

            # ── Location filter ────────────────────────────────────────────
            if not _location_match(location, loc):
                continue

            # ── Date ───────────────────────────────────────────────────────
            # createdAt is Unix timestamp in MILLISECONDS
            created_at = item.get("createdAt")
            posted_dt  = _parse_lever_date(created_at)
            posted_text = (
                posted_dt.strftime("%Y-%m-%d") if posted_dt else ""
            )

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
