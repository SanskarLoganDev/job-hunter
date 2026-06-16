"""
scrapers/ashby.py

Scrapes the Ashby public Job Postings API for any company on their platform.

API reference: https://developers.ashbyhq.com/docs/public-job-posting-api

Why the PUBLIC API is the right choice (not the authenticated jobPosting.list):
  - The authenticated API requires an employer-issued API key from a paying
    Ashby account. You'd need to be a recruiter at each company to get one.
  - The public posting API requires ZERO auth and is explicitly designed for
    candidates and career page builders.
  - Crucially, the public API returns `publishedAt` — the exact UTC timestamp
    when the job was published externally. This is more accurate than
    Greenhouse's `updated_at` (which changes on any edit, not just on publish).

API endpoint:
  GET https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}

Response shape (simplified):
  {
    "apiVersion": "1",
    "jobs": [
      {
        "title": "Software Engineer",
        "location": "San Francisco, CA",
        "secondaryLocations": [
          { "location": "New York", "address": { "addressCountry": "USA" } }
        ],
        "department": "Engineering",
        "isListed": true,
        "isRemote": true,
        "workplaceType": "Remote",           // "Remote" | "OnSite" | "Hybrid"
        "publishedAt": "2026-06-14T10:00:00.000Z",
        "employmentType": "FullTime",
        "jobUrl": "https://jobs.ashbyhq.com/company/job-id",
        "applyUrl": "https://jobs.ashbyhq.com/company/job-id/application"
      }
    ]
  }

LOCATION NOTES:
  Ashby provides a primary `location` string and `secondaryLocations` list.
  For remote roles, `isRemote` is True and `workplaceType` is "Remote".
  We build a combined location string from all available fields so the
  location filter works correctly for both office and remote roles.

HOW TO CUSTOMISE (no code changes needed):
  - add/remove role keywords  → config-ashby.yaml  keywords
  - change location filters   → config-ashby.yaml  locations
  - change the age cutoff     → config-ashby.yaml  max_age_days
  - add a new company         → new block in config-ashby.yaml with ats: ashby
  - pause a company           → config-ashby.yaml  active: false
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
API_BASE     = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
HTTP_TIMEOUT = 20


# ---------------------------------------------------------------------------
# UTC helper
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_ashby_date(date_str: str) -> Optional[datetime]:
    """
    Parse an Ashby ISO 8601 publishedAt string into a timezone-aware datetime.

    Ashby format: "2026-06-14T10:00:00.000Z" or "2026-06-14T10:00:00+00:00"

    Returns None if parsing fails.
    """
    if not date_str:
        return None
    try:
        # Replace Z suffix with +00:00 for Python 3.10 fromisoformat compat
        normalized = date_str.strip().replace("Z", "+00:00")
        # Strip milliseconds: .000+00:00 → +00:00
        normalized = re.sub(r"\.\d+(\+)", r"\1", normalized)
        return datetime.fromisoformat(normalized)
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Location builder
# ---------------------------------------------------------------------------

def _build_location(item: dict) -> str:
    """
    Build a single location string from Ashby's location fields.

    Ashby provides three sources:
      1. item["location"]             — primary location string, e.g. "San Francisco, CA"
      2. item["secondaryLocations"]   — list of additional locations
      3. item["isRemote"] / item["workplaceType"] — remote flag

    We combine them into one string so the location filter can match any part.

    Examples:
      "San Francisco, CA"
      "San Francisco, CA; New York, NY"
      "Remote"
      "San Francisco, CA; Remote"
      "New York, NY; Remote"
    """
    parts = []

    # Primary location
    primary = (item.get("location") or "").strip()
    if primary:
        parts.append(primary)

    # Secondary locations — each has a "location" string
    for sec in item.get("secondaryLocations") or []:
        loc_name = ""
        if isinstance(sec, dict):
            loc_name = (sec.get("location") or "").strip()
            if not loc_name:
                # Fall back to address fields
                addr = sec.get("address") or {}
                city    = addr.get("addressLocality", "")
                region  = addr.get("addressRegion", "")
                country = addr.get("addressCountry", "")
                loc_name = ", ".join(filter(None, [city, region, country]))
        if loc_name and loc_name not in parts:
            parts.append(loc_name)

    # Remote flag — append "Remote" so filters like locations: [Remote] work
    is_remote     = item.get("isRemote", False)
    workplace     = (item.get("workplaceType") or "").strip()
    if is_remote or workplace.lower() in ("remote", "hybrid"):
        label = "Remote" if workplace.lower() != "hybrid" else "Hybrid"
        if label not in parts:
            parts.append(label)

    return "; ".join(parts) if parts else ""


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
    """Return True if location string contains at least one allowed term."""
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
    Fetch all published jobs from the Ashby public posting API.

    No authentication required. Returns raw list of job dicts or [] on failure.
    """
    url = API_BASE.format(slug=slug)
    try:
        r = session.get(url, timeout=HTTP_TIMEOUT)
        if not r.ok:
            return []
        data = r.json()
        jobs = data.get("jobs", [])
        return jobs if isinstance(jobs, list) else []
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
    Scrape all open jobs for an Ashby company and return matching ones.

    Filters applied in order:
      1. isListed check   — only publicly listed jobs (skips internal/unlisted)
      2. Keyword match    — title must contain at least one keyword
      3. Seniority filter — excludes staff/senior/principal/lead/director/manager
      4. Location filter  — combined location string must match at least one term
      5. Age filter       — publishedAt must be within max_age_days

    Args:
        slug:         Ashby job board name from the URL. e.g. "cohere", "notion"
                      From config-ashby.yaml → slug.
        keywords:     Role title substrings. From config-ashby.yaml → keywords.
        company_name: Display name. From config-ashby.yaml → name.
        locations:    Location substrings. From config-ashby.yaml → locations.
        max_age_days: Discard jobs older than this. 0 = no filter.
                      From config-ashby.yaml → max_age_days.

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

            # ── Skip unlisted jobs ─────────────────────────────────────────
            # isListed=False means the company set it as internal/unlisted.
            # The public API can still return these; we skip them.
            if not item.get("isListed", True):
                continue

            # ── Title ─────────────────────────────────────────────────────
            title = (item.get("title") or "").strip()
            if not title:
                continue

            # ── Keyword filter ─────────────────────────────────────────────
            if not _keyword_match(title, keywords):
                continue

            # ── Seniority filter ───────────────────────────────────────────
            if not is_junior_enough(title):
                continue

            # ── Link ───────────────────────────────────────────────────────
            # Prefer jobUrl (the listing page) over applyUrl (the form)
            link = (item.get("jobUrl") or item.get("applyUrl") or "").strip()
            if not link:
                continue

            # ── Location ───────────────────────────────────────────────────
            # Build combined string from all Ashby location fields
            location = _build_location(item)

            # ── Location filter ────────────────────────────────────────────
            if not _location_match(location, loc):
                continue

            # ── Date ───────────────────────────────────────────────────────
            # Ashby provides publishedAt — the actual public publish timestamp.
            # This is more accurate than Greenhouse's updated_at.
            date_str  = item.get("publishedAt") or ""
            posted_dt = _parse_ashby_date(date_str)
            posted_text = date_str[:10] if date_str else ""  # "2026-06-14"

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
