"""
scrapers/smartrecruiters.py

Scrapes the SmartRecruiters public Posting API for any company on their platform.

API reference: https://developers.smartrecruiters.com/docs/posting-api

Why the public Posting API is the right choice:
  - Requires ZERO authentication — explicitly documented as one of the only
    SmartRecruiters endpoints accessible "Without Authentication".
  - Same shape/spirit as Greenhouse: GET request, JSON response, no browser.
  - Returns `releasedDate` — an actual publish timestamp.

API endpoints:
  List:   GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings?offset=0&limit=100
  Detail: GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings/{id}

Response shape — list endpoint (simplified):
  {
    "offset": 0,
    "limit": 100,
    "totalFound": 4619,
    "content": [
      {
        "id": "744000135041540",
        "name": "Network Communication Embedded Software Engineer",
        "releasedDate": "2026-06-30T15:04:54.879Z",
        "company": { "identifier": "BoschGroup", "name": "Bosch Group" },
        "location": {
          "city": "Braga", "region": "Braga", "country": "pt",
          "remote": false, "hybrid": true
        },
        "ref": "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/744000135041540"
      },
      ...
    ]
  }

Response shape — detail endpoint adds the human-facing URL:
  {
    ...
    "postingUrl": "https://jobs.smartrecruiters.com/BoschGroup/744000135041540-...",
    "applyUrl": "https://jobs.smartrecruiters.com/BoschGroup/744000135041540-...?oga=true",
    "active": true
  }

WHY A DETAIL FETCH IS NEEDED (unlike Greenhouse/Ashby/Lever):
  The list endpoint only returns `ref` — an API URL, not a page a human can
  open. The real careers-page link (`postingUrl`) only exists on the detail
  endpoint. So this scraper does a cheap second GET per *candidate* job
  (only for jobs that already passed keyword + seniority + location + age
  filters) to fetch just the link — never the full job description, to keep
  runtime down. This mirrors the existing Amazon scraper's
  `detail_fetch_limit` pattern.

IDENTIFIER NOTES:
  SmartRecruiters' `companyIdentifier` is NOT always the obvious brand name
  (e.g. Bosch is "BoschGroup", not "bosch"). Verify via the public careers
  URL: https://careers.smartrecruiters.com/{identifier} or
  https://jobs.smartrecruiters.com/{identifier} before adding a company.

LOCATION NOTES:
  SmartRecruiters location is structured: city / region / country / remote
  (bool) / hybrid (bool) — cleaner than Greenhouse. Combined into one string
  the same way Ashby's _build_location() works.

PAGINATION:
  Uses offset/limit/totalFound (not the newer cursor-based nextPageId scheme
  — that's documented for other SmartRecruiters APIs, not this one). Loops
  `offset += limit` until all pages are fetched or max_pages is hit, to
  avoid one company with thousands of postings stalling the whole poll run.

HOW TO CUSTOMISE (no code changes needed):
  - add/remove role keywords  → config-smartrecruiters.yaml  keywords
  - change location filters   → config-smartrecruiters.yaml  locations
  - change the age cutoff     → config-smartrecruiters.yaml  max_age_days
  - add a new company         → new block in config-smartrecruiters.yaml
  - pause a company           → config-smartrecruiters.yaml  active: false
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
LIST_URL_TMPL   = "https://api.smartrecruiters.com/v1/companies/{identifier}/postings"
DETAIL_URL_TMPL = "https://api.smartrecruiters.com/v1/companies/{identifier}/postings/{posting_id}"
HTTP_TIMEOUT    = 20
PAGE_LIMIT      = 100   # max page size the API supports well
MAX_PAGES       = 20    # hard cap — 2000 postings/company before we stop paging


# ---------------------------------------------------------------------------
# UTC helper
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_sr_date(date_str: str) -> Optional[datetime]:
    """
    Parse a SmartRecruiters ISO 8601 releasedDate string into a
    timezone-aware datetime.

    Format: "2026-06-30T15:04:54.879Z"

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
# Location builder
# ---------------------------------------------------------------------------

def _build_location(item: dict) -> str:
    """
    Build a single location string from SmartRecruiters' structured location.

    SmartRecruiters provides:
      location.city / region / country  — plain strings
      location.remote / hybrid          — booleans

    Examples:
      "Braga, Braga, pt"
      "Pune, , in; Hybrid"
      "Remote"
    """
    loc = item.get("location") or {}
    if not isinstance(loc, dict):
        return ""

    parts = []
    city    = (loc.get("city") or "").strip()
    region  = (loc.get("region") or "").strip()
    country = (loc.get("country") or "").strip()

    main = ", ".join(filter(None, [city, region, country]))
    if main:
        parts.append(main)

    if loc.get("remote"):
        parts.append("Remote")
    if loc.get("hybrid"):
        parts.append("Hybrid")

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
# Core fetch — paginated list
# ---------------------------------------------------------------------------

def _fetch_jobs(identifier: str, session: requests.Session) -> List[dict]:
    """
    Fetch all postings from the SmartRecruiters public Posting API for the
    given company identifier, paginating via offset/limit until exhausted
    or MAX_PAGES is hit. Returns raw list of posting dicts, or [] on failure.
    """
    url = LIST_URL_TMPL.format(identifier=identifier)
    all_jobs: List[dict] = []
    offset = 0

    for _ in range(MAX_PAGES):
        try:
            r = session.get(
                url,
                params={"offset": offset, "limit": PAGE_LIMIT},
                timeout=HTTP_TIMEOUT,
            )
            if not r.ok:
                break
            data = r.json()
        except Exception:
            break

        content = data.get("content", [])
        if not isinstance(content, list) or not content:
            break

        all_jobs.extend(content)

        total_found = data.get("totalFound", 0)
        offset += PAGE_LIMIT
        if offset >= total_found:
            break

        time.sleep(random.uniform(0.3, 0.6))  # be polite between pages

    return all_jobs


# ---------------------------------------------------------------------------
# Detail fetch — gets the human-facing postingUrl
# ---------------------------------------------------------------------------

def _fetch_posting_url(
    identifier: str,
    posting_id: str,
    session: requests.Session,
) -> str:
    """
    Fetch the detail endpoint for a single posting to get postingUrl —
    the actual jobs.smartrecruiters.com link. Returns "" on any failure.
    Only called for jobs that already passed all filters, to limit requests.
    """
    url = DETAIL_URL_TMPL.format(identifier=identifier, posting_id=posting_id)
    try:
        r = session.get(url, timeout=HTTP_TIMEOUT)
        if not r.ok:
            return ""
        data = r.json()
        return (data.get("postingUrl") or data.get("applyUrl") or "").strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape(
    slug: str,
    keywords: List[str],
    company_name: str,
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
    detail_fetch_limit: int = 30,
) -> List[Job]:
    """
    Scrape all open jobs for a SmartRecruiters company and return matching ones.

    Filters applied in order:
      1. Keyword match    — title must contain at least one keyword
      2. Seniority filter — excludes staff/senior/principal/lead etc.
      3. Location filter  — combined location string must match at least one term
      4. Age filter       — releasedDate must be within max_age_days
      5. Detail fetch      — only for jobs that survive 1-4, fetch postingUrl
                             (capped at detail_fetch_limit per run, mirrors Amazon)

    Args:
        slug:                SmartRecruiters companyIdentifier (NOT always the
                             obvious brand name — verify via careers.smartrecruiters.com/{slug}).
                             From config-smartrecruiters.yaml → slug.
        keywords:            Role title substrings.
        company_name:        Display name.
        locations:           Location substrings.
        max_age_days:        Discard jobs older than this. 0 = no filter.
        detail_fetch_limit:  Max number of detail-endpoint calls per run, to
                             cap runtime for companies with many matching jobs.

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
        candidates: List[dict] = []

        for item in raw_jobs:
            # ── Title ─────────────────────────────────────────────────────
            title = (item.get("name") or "").strip()
            if not title:
                continue

            # ── Keyword filter ───────────────────────────────────────────
            if not _keyword_match(title, keywords):
                continue

            # ── Seniority filter ─────────────────────────────────────────
            if not is_junior_enough(title):
                continue

            # ── Location ──────────────────────────────────────────────────
            location = _build_location(item)

            # ── Location filter ───────────────────────────────────────────
            if not _location_match(location, loc):
                continue

            # ── Date ──────────────────────────────────────────────────────
            date_str  = item.get("releasedDate") or ""
            posted_dt = _parse_sr_date(date_str)
            posted_text = date_str[:10] if date_str else ""

            # ── Age filter ────────────────────────────────────────────────
            if cutoff is not None:
                if posted_dt is None or posted_dt < cutoff:
                    continue

            posting_id = str(item.get("id") or "").strip()
            if not posting_id:
                continue

            candidates.append({
                "title": title,
                "posting_id": posting_id,
                "location": location,
                "posted_text": posted_text,
                "posted_dt": posted_dt,
            })

        # ── Detail fetch for postingUrl — capped at detail_fetch_limit ──────
        results: List[Job] = []
        fetched = 0
        for c in candidates:
            if fetched >= detail_fetch_limit:
                break
            link = _fetch_posting_url(slug, c["posting_id"], session)
            fetched += 1
            time.sleep(random.uniform(0.2, 0.5))

            if not link:
                continue

            results.append(Job(
                title=c["title"],
                company=company_name,
                link=link,
                location=c["location"],
                posted_text=c["posted_text"],
                posted_dt=c["posted_dt"],
            ))

        time.sleep(random.uniform(0.5, 1.5))
        return results

    except Exception:
        return []
