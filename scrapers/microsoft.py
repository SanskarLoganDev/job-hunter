"""
scrapers/microsoft.py

Scrapes apply.careers.microsoft.com for open roles via the Eightfold AI
internal search API that powers Microsoft's careers site.

DISCOVERY NOTES:
  careers.microsoft.com is the marketing/landing page (Eightfold AI frontend,
  confirmed via static.vscdn.net/fonts/css/eightfold-font-base.css in HTML).
  The old gcsservices.careers.microsoft.com endpoint is dead (SSL hostname
  mismatch). The real search API lives at apply.careers.microsoft.com:
    https://apply.careers.microsoft.com/api/pcsx/search
  Confirmed via devtools Network tab on:
    https://apply.careers.microsoft.com/careers?start=0&location=United+States...
  No auth required. Returns clean JSON. No Cloudflare protection on the API.

API:
  GET https://apply.careers.microsoft.com/api/pcsx/search
  No authentication. Returns JSON.

KEY PARAMS:
  domain=microsoft.com        Required — identifies the tenant
  query=                      Keyword search (empty = all roles)
  location=United States, Multiple Locations, Multiple Locations
                              Location filter — exact string from the UI
  start=0                     Pagination offset (10 results per page)
  sort_by=timestamp           Sort by posting date, newest first
  filter_include_remote=1     Include remote roles
  filter_seniority=Mid-Level  Seniority filter — API-side (but not strict,
  filter_seniority=Entry      is_junior_enough() still needed as second gate)

RESPONSE SHAPE:
  {
    "status": 200,
    "data": {
      "count": 81,              ← total matching jobs
      "positions": [
        {
          "id": 1970393556917835,
          "name": "Software Engineer",
          "locations": ["United States, Washington, Redmond"],
          "standardizedLocations": ["Redmond, WA, US"],
          "postedTs": 1784228545,    ← Unix timestamp, SECONDS
          "workLocationOption": "onsite" | "remote" | "hybrid",
          "department": "Software Engineering",
          "positionUrl": "/careers/job/1970393556917835"
        },
        ...
      ]
    }
  }

LINK:
  positionUrl is a relative path — prepend BASE_URL to get the full link.
  No detail fetch needed.

PAGINATION:
  data.count = total results. Page size = 10 (fixed by API).
  Loop start += 10 until exhausted or MAX_PAGES hit.

SENIORITY:
  API-side filter_seniority=Entry&Mid-Level is applied but not perfectly strict
  (Senior/Principal titles still appear). is_junior_enough() applied as second
  gate — same as all other scrapers.

LOCATION:
  locations[] is an array of "Country, State, City" strings.
  standardizedLocations[] is an array of "City, ST, US" strings.
  Scraper joins all standardized locations into one string for display and
  appends workLocationOption if remote/hybrid.

HOW TO CUSTOMISE:
  - keywords        → config/config-microsoft.yaml  keywords
  - max_age_days    → config/config-microsoft.yaml  max_age_days
  - pause           → config/config-microsoft.yaml  active: false
  - seniority terms → scrapers/__init__.py  _SENIOR_TERMS
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
BASE_URL    = "https://apply.careers.microsoft.com"
SEARCH_URL  = f"{BASE_URL}/api/pcsx/search"
PAGE_SIZE   = 10     # fixed by the API
MAX_PAGES   = 30     # hard cap: 300 jobs max before we stop paging
HTTP_TIMEOUT = 20

LOCATION_PARAM = "United States, Multiple Locations, Multiple Locations"


# ---------------------------------------------------------------------------
# UTC helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts) -> Optional[datetime]:
    """Convert a Unix timestamp (seconds) to UTC-aware datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Location builder
# ---------------------------------------------------------------------------

def _build_location(position: dict) -> str:
    """
    Build a display location string from standardizedLocations[] and
    workLocationOption.

    standardizedLocations: ["Redmond, WA, US", "Seattle, WA, US"]
    workLocationOption: "onsite" | "remote" | "hybrid"

    For remote/hybrid, append the label. Cap at 3 locations to avoid
    very long strings when a role is posted in many cities.
    """
    std = position.get("standardizedLocations") or []
    if not isinstance(std, list):
        std = []

    parts = [s.strip() for s in std if s and s.strip()][:3]
    location = "; ".join(parts)

    opt = (position.get("workLocationOption") or "").lower()
    if opt == "remote":
        location = (location + "; Remote").lstrip("; ")
    elif opt == "hybrid":
        location = (location + "; Hybrid").lstrip("; ")

    return location


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def _keyword_match(title: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    t = title.lower()
    return any(k.lower() in t for k in keywords)


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
        "Referer":         f"{BASE_URL}/",
        "Origin":          BASE_URL,
    })
    return s


# ---------------------------------------------------------------------------
# Core fetch — one keyword query, paginated
# ---------------------------------------------------------------------------

def _fetch_all(keyword: str, session: requests.Session) -> List[dict]:
    """
    Fetch all matching positions for one keyword query, paginating via
    start offset until exhausted or MAX_PAGES hit.
    Returns raw list of position dicts.
    """
    all_positions: List[dict] = []
    start = 0

    for _ in range(MAX_PAGES):
        params = [
            ("domain",                "microsoft.com"),
            ("query",                 keyword),
            ("location",              LOCATION_PARAM),
            ("start",                 str(start)),
            ("sort_by",               "timestamp"),
            ("filter_include_remote", "1"),
            ("filter_seniority",      "Mid-Level"),
            ("filter_seniority",      "Entry"),
        ]
        try:
            r = session.get(SEARCH_URL, params=params, timeout=HTTP_TIMEOUT)
            if not r.ok:
                break
            data = r.json()
        except Exception:
            break

        positions = (data.get("data") or {}).get("positions") or []
        if not isinstance(positions, list) or not positions:
            break

        all_positions.extend(positions)

        total = (data.get("data") or {}).get("count") or 0
        start += PAGE_SIZE
        if start >= total:
            break

        time.sleep(random.uniform(0.3, 0.6))

    return all_positions


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape(
    keywords: List[str],
    company_name: str = "Microsoft",
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
) -> List[Job]:
    """
    Scrape Microsoft's careers site for matching US roles.

    Queries the Eightfold AI search API with each keyword individually
    (the API does exact keyword matching against titles — empty query returns
    all roles, which we then filter ourselves). Dedupes by position id.

    API-side seniority filter (Entry + Mid-Level) is applied but imperfect —
    is_junior_enough() applied as a second gate, same as all other scrapers.

    No `slug` needed — single fixed tenant (domain=microsoft.com).
    `locations` param accepted for interface compatibility but unused —
    the API already filters to United States.

    Returns List[Job], empty on any failure, never raises.
    """
    try:
        session  = _make_session()
        cutoff   = _now() - timedelta(days=max_age_days) if max_age_days > 0 else None

        # Fetch with each keyword and dedup by position id
        seen_ids: set = set()
        raw_positions: List[dict] = []

        # If no keywords, do a single empty-query fetch
        queries = keywords if keywords else [""]

        for kw in queries:
            positions = _fetch_all(kw, session)
            for p in positions:
                pid = p.get("id")
                if pid is None or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                raw_positions.append(p)
            time.sleep(random.uniform(0.5, 1.0))

        results: List[Job] = []

        for item in raw_positions:
            # ── Title ─────────────────────────────────────────────────────
            title = (item.get("name") or "").strip()
            if not title:
                continue

            # ── Keyword filter ────────────────────────────────────────────
            if not _keyword_match(title, keywords):
                continue

            # ── Seniority filter ──────────────────────────────────────────
            if not is_junior_enough(title):
                continue

            # ── Link ──────────────────────────────────────────────────────
            position_url = (item.get("positionUrl") or "").strip()
            if not position_url:
                continue
            link = BASE_URL + position_url

            # ── Location ──────────────────────────────────────────────────
            location = _build_location(item)

            # ── Date ──────────────────────────────────────────────────────
            posted_dt   = _parse_ts(item.get("postedTs"))
            posted_text = posted_dt.strftime("%Y-%m-%d") if posted_dt else ""

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
