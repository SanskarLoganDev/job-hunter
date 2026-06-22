"""
scrapers/workable.py

Scrapes the Workable public widget API for any company on their platform.

API reference: https://apply.workable.com/api/v1/widget/accounts/{slug}

Why this API is clean:
  - No authentication required — the widget endpoint is intentionally public.
  - Location is returned as a structured object with country_code, city, region
    separately — much cleaner than Greenhouse's concatenated string.
  - This means we can filter on country_code == "US" directly instead of
    substring matching location names.
  - The response includes a `created_at` ISO timestamp (actual publish date).

Response shape (simplified):
  {
    "account": { "name": "Acme", "url": "https://apply.workable.com/acme" },
    "jobs": [
      {
        "id": "ABC123",
        "title": "Software Engineer",
        "shortlink": "https://apply.workable.com/acme/j/ABC123/",
        "url": "https://apply.workable.com/acme/j/ABC123/",
        "location": {
          "location_str": "Portland, Oregon, United States",
          "country": "United States",
          "country_code": "US",
          "region": "Oregon",
          "region_code": "OR",
          "city": "Portland",
          "zip_code": "97201",
          "telecommuting": false
        },
        "created_at": "2026-06-01T10:00:00Z",
        "employment_type": "full-time",
        "department": "Engineering",
        "remote": false
      }
    ]
  }

HOW TO FIND THE SLUG:
  Go to https://apply.workable.com/{SLUG} — if the page loads, the slug is correct.

HOW TO CUSTOMISE (no code changes needed):
  - add/remove role keywords  → config/config-workable.yaml  keywords
  - change the age cutoff     → config/config-workable.yaml  max_age_days
  - add a new company         → new block in config/config-workable.yaml
  - pause a company           → config/config-workable.yaml  active: false
  - seniority exclusions      → scrapers/__init__.py  _SENIOR_TERMS

LOCATION NOTES:
  Workable returns structured location data — we use country_code directly.
  For US roles: country_code == "US"
  For remote roles: location.telecommuting == true OR location may be null
  The locations list in config is therefore simpler — just ["US"] usually works,
  or leave empty [] to get all locations including international.
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
API_BASE     = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
HTTP_TIMEOUT = 20


# ---------------------------------------------------------------------------
# UTC helper
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_workable_date(date_str: str) -> Optional[datetime]:
    """
    Parse a Workable ISO 8601 created_at string into a timezone-aware datetime.

    Workable format: "2026-06-01T10:00:00Z" or "2026-06-01T10:00:00+00:00"

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


def _location_allowed(job: dict, allowed: List[str]) -> bool:
    """
    Return True if the job's location passes the filter.

    Workable provides structured location data, so we can:
      1. Check country_code directly for "US" — no substring guessing needed
      2. Check telecommuting flag for remote roles
      3. Fall back to location_str substring match if needed

    If allowed list is empty, everything passes.
    """
    if not allowed:
        return True

    loc = job.get("location") or {}

    # Handle null location (some remote-only roles have no location object)
    if not loc:
        # Only pass through if "Remote" is in allowed
        return any(a.lower() in ("remote", "anywhere") for a in allowed)

    country_code = (loc.get("country_code") or "").upper()
    city         = (loc.get("city") or "").lower()
    region       = (loc.get("region") or "").lower()
    loc_str      = (loc.get("location_str") or "").lower()
    is_remote    = loc.get("telecommuting", False) or job.get("remote", False)

    allowed_lower = [a.lower() for a in allowed]

    for term in allowed_lower:
        if term in ("us", "usa", "united states"):
            if country_code == "US":
                return True
        elif term == "remote":
            if is_remote:
                return True
        else:
            # City or region substring match
            if term in city or term in region or term in loc_str:
                return True

    return False


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
    Fetch all published jobs from the Workable public widget API.
    No authentication required.
    Returns raw list of job dicts or [] on failure.
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
    Scrape all published jobs for a Workable company and return matching ones.

    Filters applied in order:
      1. Keyword match    — title must contain at least one keyword
      2. Seniority filter — excludes staff/senior/principal/lead/director/manager
      3. Location filter  — uses structured country_code/telecommuting fields
                           "US" in locations list matches country_code == "US"
                           "Remote" matches telecommuting == true
      4. Age filter       — created_at must be within max_age_days

    Args:
        slug:         Workable account subdomain. e.g. "typeform", "intercom"
                      Verify at: https://apply.workable.com/{slug}
        keywords:     Role title substrings. From config-workable.yaml → keywords.
        company_name: Display name. From config-workable.yaml → name.
        locations:    Filter terms. Use ["US"] for US-only, ["US", "Remote"] for both.
                      From config-workable.yaml → locations. [] = no filter.
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
            # Prefer shortlink (clean) over full url
            link = (
                item.get("shortlink") or
                item.get("url") or
                item.get("application_url") or ""
            ).strip()
            if not link:
                continue

            # ── Location ───────────────────────────────────────────────────
            loc_obj  = item.get("location") or {}
            location = (loc_obj.get("location_str") or "").strip()
            # Append Remote flag if telecommuting
            if item.get("remote") or loc_obj.get("telecommuting"):
                if "remote" not in location.lower():
                    location = (location + "; Remote").strip("; ")

            # ── Location filter ────────────────────────────────────────────
            if not _location_allowed(item, loc):
                continue

            # ── Date ───────────────────────────────────────────────────────
            date_str  = item.get("created_at") or ""
            posted_dt = _parse_workable_date(date_str)
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
