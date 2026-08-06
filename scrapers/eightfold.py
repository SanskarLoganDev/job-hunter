"""
scrapers/eightfold.py

Generic scraper for any company running Eightfold AI as their careers
platform ("PCSX" product). Works via the public search API that powers
the careers site frontend — no auth required.

ORIGIN:
  Started as scrapers/microsoft.py (Microsoft-only). Generalized after
  discovering CBTS runs the identical platform/API — confirmed via a
  direct API call returning the same response shape (positions[],
  standardizedLocations[], postedTs, workLocationOption, positionUrl).
  Any future Eightfold-based company is now a config-only addition —
  no new scraper file needed.

  How to spot an Eightfold-based ATS: the careers site calls
  <base_url>/api/pcsx/search and returns this exact JSON shape. Often
  visible in the page's embedded config as "pcsxConfig" or asset URLs
  under static.vscdn.net.

API:
  GET {base_url}/api/pcsx/search
  No authentication. Returns JSON.

KEY PARAMS:
  domain=<tenant domain>      Required — identifies the tenant (e.g. "microsoft.com", "cbts.com")
  query=                      Keyword search (empty = all roles)
  location=...                Location filter — exact string from the UI
  start=0                     Pagination offset (10 results per page)
  sort_by=timestamp           Sort by posting date, newest first
  filter_include_remote=1     Include remote roles
  filter_seniority=Mid-Level  Seniority filter — API-side (imperfect,
  filter_seniority=Entry      is_junior_enough() still needed as second gate)

RESPONSE SHAPE:
  {
    "status": 200,
    "data": {
      "count": <int>,
      "positions": [
        {
          "id": <int>,
          "name": "Software Engineer",
          "locations": [...],
          "standardizedLocations": ["Cincinnati, OH, US"],
          "postedTs": <unix seconds>,
          "workLocationOption": "onsite" | "remote_local" | "remote_global" | "hybrid",
          "positionUrl": "/careers/job/<id>"
        },
        ...
      ]
    }
  }

  NOTE: CBTS's workLocationOption uses "remote_local"/"remote_global" instead
  of Microsoft's plain "remote" — scraper checks for any value STARTING WITH
  "remote" to catch both tenants' conventions.

PER-COMPANY CONFIG (config/config-eightfold.yaml):
  Each company entry needs:
    domain          — tenant identifier, e.g. "cbts.com"
    base_url        — scheme + host, e.g. "https://jobs.cbts.com"
    location_param  — the exact "location" query string the UI sends
                       (varies per tenant — check devtools). Falls back to
                       "United States" if omitted.

LINK:
  positionUrl is a relative path — prepend base_url to get the full link.

PAGINATION:
  data.count = total results. Page size = 10 (fixed by API).
  Loop start += 10 until exhausted or MAX_PAGES hit.

SENIORITY:
  API-side filter_seniority=Entry&Mid-Level applied but not strict.
  is_junior_enough() applied as second gate — same as all other scrapers.

MULTI-TENANT MICROSITES (not implemented, flagged for later):
  Some Eightfold instances serve more than one company off the same
  domain via a `microsite` filter — e.g. CBTS's instance also serves
  "OnX Enterprise Solutions" (confirmed in the site's public config
  under configs.pcsxConfig.microsite.onx). Adding this would need an
  extra `company_filter` fq param scoped per microsite. Not built —
  next session if OnX is wanted as a separate config entry.

HOW TO ADD A NEW EIGHTFOLD COMPANY:
  1. Confirm the platform: open the careers URL, check devtools Network
     tab for a request to <base_url>/api/pcsx/search.
  2. Note the `domain` param value from that request (usually the
     company's root domain).
  3. Add an entry to config/config-eightfold.yaml with name, base_url,
     domain, location_param, keywords, locations, max_age_days, active: true.
  4. No code changes needed.

HOW TO CUSTOMISE:
  - keywords         → config/config-eightfold.yaml  keywords (per company)
  - max_age_days     → config/config-eightfold.yaml  max_age_days
  - pause            → config/config-eightfold.yaml  active: false
  - seniority terms  → scrapers/__init__.py  _SENIOR_TERMS
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
PAGE_SIZE    = 10     # fixed by the API
MAX_PAGES    = 30     # hard cap: 300 jobs max before we stop paging
HTTP_TIMEOUT = 20

DEFAULT_LOCATION_PARAM = "United States"


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
    workLocationOption: "onsite" | "remote_local" | "remote_global" | "hybrid"

    Caps at 3 locations to avoid very long strings when a role is posted
    in many cities.
    """
    std = position.get("standardizedLocations") or []
    if not isinstance(std, list):
        std = []

    parts = [s.strip() for s in std if s and s.strip()][:3]
    location = "; ".join(parts)

    opt = (position.get("workLocationOption") or "").lower()
    if opt.startswith("remote"):
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

def _make_session(base_url: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         f"{base_url}/",
        "Origin":          base_url,
    })
    return s


# ---------------------------------------------------------------------------
# Core fetch — one keyword query, paginated
# ---------------------------------------------------------------------------

def _fetch_all(
    keyword: str,
    session: requests.Session,
    base_url: str,
    domain: str,
    location_param: str,
) -> List[dict]:
    """
    Fetch all matching positions for one keyword query against one tenant,
    paginating via start offset until exhausted or MAX_PAGES hit.
    Returns raw list of position dicts.
    """
    all_positions: List[dict] = []
    start = 0
    search_url = f"{base_url}/api/pcsx/search"

    for _ in range(MAX_PAGES):
        params = [
            ("domain",                domain),
            ("query",                 keyword),
            ("location",              location_param),
            ("start",                 str(start)),
            ("sort_by",               "timestamp"),
            ("filter_include_remote", "1"),
            ("filter_seniority",      "Mid-Level"),
            ("filter_seniority",      "Entry"),
        ]
        try:
            r = session.get(search_url, params=params, timeout=HTTP_TIMEOUT)
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
    company_name: str = "",
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
    domain: str = "",
    base_url: str = "",
    location_param: str = "",
) -> List[Job]:
    """
    Scrape an Eightfold-AI-powered careers site for matching US roles.

    `domain` and `base_url` are required — they identify which Eightfold
    tenant to query (see config/config-eightfold.yaml for per-company
    values). `location_param` overrides the default "United States" query
    string if the tenant's UI sends something more specific (check devtools
    on that company's careers site if results look off).

    Queries the Eightfold AI search API with an empty keyword query (the API
    does exact keyword matching against titles; empty = all roles), then
    filters locally via _keyword_match() — same result as querying per
    keyword but with far fewer requests.

    API-side seniority filter (Entry + Mid-Level) is applied but imperfect —
    is_junior_enough() applied as a second gate, same as all other scrapers.

    `locations` param accepted for interface compatibility but unused — the
    API already filters to the tenant's location_param (typically US).

    Returns List[Job], empty on any failure (including missing
    domain/base_url), never raises.
    """
    if not domain or not base_url:
        return []

    try:
        session   = _make_session(base_url)
        cutoff    = _now() - timedelta(days=max_age_days) if max_age_days > 0 else None
        loc_param = location_param or DEFAULT_LOCATION_PARAM

        raw_positions: List[dict] = []
        seen_ids: set = set()

        for p in _fetch_all("", session, base_url, domain, loc_param):
            pid = p.get("id")
            if pid is None or pid in seen_ids:
                continue
            seen_ids.add(pid)
            raw_positions.append(p)

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
            link = base_url + position_url

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
