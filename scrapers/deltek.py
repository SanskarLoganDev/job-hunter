"""
scrapers/deltek.py

Scrapes careers.deltek.com for open roles via the Symphony Talent
(m-cloud.io) internal jobs API that powers the careers site.

DISCOVERY NOTES:
  The careers site (careers.deltek.com) is WordPress + CWS plugin.
  The CWS plugin exposes only /wp-json/cws/autocomplete (search suggestions).
  The actual job data is fetched directly from the browser to:
    https://jobsapi-internal.m-cloud.io/api/job
  No server-side proxy — this is a direct, unauthenticated GET from the
  browser, confirmed via devtools Network tab.

API:
  GET https://jobsapi-internal.m-cloud.io/api/job
  No authentication. Returns JSON. No JSONP wrapper needed (callback param
  is optional and only used by the CWS frontend; omitting it gives clean JSON).

KEY PARAMS:
  Organization=2458           Deltek's tenant ID (from cws_opts.org in page HTML)
  facet[]=ats_portalid:Kenexa Kenexa/BrassRing ATS filter (required — without
                              it the query returns 0 results)
  facet[]=education:United States  Country filter (education field = country)
  facet[]=primary_category:X      Category filter
  sortfield=open_date         Sort by posting date
  sortorder=descending        Newest first
  Limit=100                   Page size
  offset=0                    Pagination offset

CATEGORY FILTER BEHAVIOUR (AND, not OR):
  Two facet[]=primary_category params in the same request are treated as AND,
  which returns 0 results since a job can only have one category. The two
  relevant categories ("Information Technology" and "Software Development/Design")
  must be fetched in SEPARATE requests and deduped by job ID. This scraper
  does exactly that.

JOB OBJECT FIELDS (relevant subset):
  id              int       unique job ID — used as dedup key
  title           str       job title
  open_date       str       "MM/DD/YYYY HH:MM:SS"  posting date
  url             str       https://careers.deltek.com/job/{id}/{slug}/
  primary_city    str       city name
  primary_state   str       state abbreviation e.g. "VA"
  primary_country str       ISO country code e.g. "US"
  education       str       country name e.g. "United States" (used as location filter)
  primary_category str      e.g. "Information Technology"
  totalHits       int       total matching jobs (top-level, not per-job)

LINK:
  `url` field contains the clean careers.deltek.com link — no detail fetch
  needed, unlike SmartRecruiters. One less HTTP call per job.

PAGINATION:
  totalHits tells us total count. Loop offset += Limit until exhausted.
  Capped at MAX_PAGES for safety.

HOW TO CUSTOMISE (no code changes needed):
  - add/remove keywords    → config/config-deltek.yaml  keywords
  - change age cutoff      → config/config-deltek.yaml  max_age_days
  - pause Deltek           → config/config-deltek.yaml  active: false
  - seniority exclusions   → scrapers/__init__.py  _SENIOR_TERMS
"""

import time
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from scrapers import Job, is_junior_enough

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_URL      = "https://jobsapi-internal.m-cloud.io/api/job"
ORGANIZATION = "2458"
PAGE_SIZE    = 100
MAX_PAGES    = 10   # safety cap: 1000 jobs max before we stop paging
HTTP_TIMEOUT = 20

# The two categories from the target URL — fetched separately (AND not OR)
CATEGORIES = [
    "Information Technology",
    "Software Development/Design",
]


# ---------------------------------------------------------------------------
# UTC helper
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_deltek_date(date_str: str) -> Optional[datetime]:
    """
    Parse Deltek's open_date field. Two formats observed in the wild:
      ISO 8601:  "2026-07-01T16:19:31.513Z"  (actual API response)
      Legacy:    "07/01/2026 16:19:31"        (seen in devtools, may vary)
    Returns UTC-aware datetime or None on failure.
    """
    if not date_str:
        return None
    s = date_str.strip()
    # ISO 8601 — most common in practice
    try:
        normalized = s.replace("Z", "+00:00")
        import re as _re
        normalized = _re.sub(r"\.\d+(\.+)", r"\1", normalized)
        normalized = _re.sub(r"\.\d+([+-])", r"\1", normalized)
        return datetime.fromisoformat(normalized)
    except (ValueError, AttributeError):
        pass
    # Legacy MM/DD/YYYY HH:MM:SS
    try:
        return datetime.strptime(s, "%m/%d/%Y %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


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
        "Accept":          "application/json, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://careers.deltek.com/",
        "Origin":          "https://careers.deltek.com",
    })
    return s


# ---------------------------------------------------------------------------
# Core fetch — one category, paginated
# ---------------------------------------------------------------------------

def _fetch_category(category: str, session: requests.Session) -> List[dict]:
    """
    Fetch all US jobs in one category, paginating until exhausted or MAX_PAGES.
    Returns raw list of job dicts (queryResult items).
    """
    all_jobs: List[dict] = []
    offset = 0

    for _ in range(MAX_PAGES):
        params = [
            ("facet[]", "ats_portalid:Kenexa"),
            ("facet[]", "education:United States"),
            ("facet[]", f"primary_category:{category}"),
            ("sortfield",  "open_date"),
            ("sortorder",  "descending"),
            ("Limit",      str(PAGE_SIZE)),
            ("Organization", ORGANIZATION),
            ("offset",     str(offset)),
        ]
        try:
            r = session.get(API_URL, params=params, timeout=HTTP_TIMEOUT)
            if not r.ok:
                break
            data = r.json()
        except Exception:
            break

        jobs = data.get("queryResult") or []
        if not isinstance(jobs, list) or not jobs:
            break

        all_jobs.extend(jobs)

        total = data.get("totalHits") or 0
        offset += PAGE_SIZE
        if offset >= total:
            break

        time.sleep(random.uniform(0.3, 0.6))

    return all_jobs


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def _keyword_match(title: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    t = title.lower()
    return any(k.lower() in t for k in keywords)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape(
    keywords: List[str],
    company_name: str = "Deltek",
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
) -> List[Job]:
    """
    Scrape Deltek's careers site for matching US jobs.

    Fetches two categories separately (Information Technology +
    Software Development/Design), dedupes by job ID, then applies
    keyword, seniority, and age filters.

    No `slug` param — Deltek is a single fixed tenant (org 2458).
    No `locations` filter applied at scraper level — the API already
    filters to `education=United States`. The locations param is accepted
    for interface compatibility but unused.

    Returns List[Job], empty on any failure, never raises.
    """
    try:
        session = _make_session()
        cutoff  = _now() - timedelta(days=max_age_days) if max_age_days > 0 else None

        # Fetch both categories and dedup by job ID
        seen_ids: set = set()
        raw_jobs: List[dict] = []

        for cat in CATEGORIES:
            jobs = _fetch_category(cat, session)
            for j in jobs:
                jid = j.get("id")
                if jid is None or jid in seen_ids:
                    continue
                seen_ids.add(jid)
                raw_jobs.append(j)
            time.sleep(random.uniform(0.5, 1.0))

        results: List[Job] = []

        for item in raw_jobs:
            # ── Title ────────────────────────────────────────────────────
            title = (item.get("title") or "").strip()
            if not title:
                continue

            # ── Keyword filter ───────────────────────────────────────────
            if not _keyword_match(title, keywords):
                continue

            # ── Seniority filter ─────────────────────────────────────────
            if not is_junior_enough(title):
                continue

            # ── Link ─────────────────────────────────────────────────────
            link = (item.get("url") or "").strip()
            if not link:
                continue

            # ── Location string ───────────────────────────────────────────
            city    = (item.get("primary_city")    or "").strip()
            state   = (item.get("primary_state")   or "").strip()
            country = (item.get("primary_country") or "").strip()
            location = ", ".join(filter(None, [city, state, country]))

            # ── Date ──────────────────────────────────────────────────────
            date_str  = (item.get("open_date") or "").strip()
            posted_dt = _parse_deltek_date(date_str)
            # Store YYYY-MM-DD for display, matching other scrapers
            posted_text = posted_dt.strftime("%Y-%m-%d") if posted_dt else date_str[:10]

            # ── Age filter ────────────────────────────────────────────────
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
