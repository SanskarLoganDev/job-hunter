"""
scrapers/google.py

Scrapes careers.google.com for open roles by fetching the search results
page HTML and extracting job data embedded in an AF_initDataCallback blob.

DISCOVERY NOTES:
  careers.google.com/jobs/results/ server-side renders job data directly
  into the HTML as AF_initDataCallback JavaScript blocks. No separate XHR/
  fetch for job data — it's all in the initial HTML response. No auth needed,
  no Cloudflare, no JS rendering required (plain requests.get() works).

  The old /api/jobs/results/ endpoint is dead (404 as of 2026).

  Data structure in HTML:
    AF_initDataCallback({key: 'ds:0', ...})  ← company metadata
    AF_initDataCallback({key: 'ds:1', ...})  ← job listings ← we use this

HOW THE DATA IS STRUCTURED:
  ds:1 data is a nested positional array (no named keys). Each job is:
    data[0][i] = one job, a positional array where:
      [0]  = job ID string  e.g. "143122286080074438"
      [1]  = title          e.g. "Software Engineer II"
      [2]  = apply URL      e.g. "https://www.google.com/about/careers/..."
      [3]  = description arrays (HTML, nested)
      [4]  = company resource path (internal)
      [5]  = null
      [6]  = company name   e.g. "Google"
      [7]  = language       e.g. "en-US"
      [8]  = locations list e.g. [["Austin, TX, USA", [...], "Austin", null, "TX", "US"], ...]
      [9]  = full description (HTML)
      [10] = seniority codes list e.g. [2, 3, 4]
      [11] = [creation_ts_sec, creation_ts_ns]
      [12] = [published_ts_sec, published_ts_ns]  ← POSTED DATE (seconds)
      [13] = [updated_ts_sec, updated_ts_ns]

  published_ts_sec = job[12][0]  e.g. 1784106609

URL PARAMS (used in page fetch):
  category=SOFTWARE_ENGINEERING   job category filter
  location=United+States          location filter
  Additional categories can be added with multiple category= params.

PAGINATION:
  The page URL supports a `page` param (1-indexed). Each page has ~20 jobs.
  Scraper iterates pages until no new jobs found or MAX_PAGES hit.

LOCATION:
  locations list at job[8] — each entry: ["City, ST, USA", [...], "City",
  zip, "ST", "US"]. Scraper joins display strings (index 0) from each entry.

HOW TO CUSTOMISE:
  - keywords      → config/config-google.yaml  keywords
  - max_age_days  → config/config-google.yaml  max_age_days
  - pause         → config/config-google.yaml  active: false
  - seniority     → scrapers/__init__.py  _SENIOR_TERMS
"""

import re
import json
import time
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from scrapers import Job, is_junior_enough

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL    = "https://careers.google.com"
SEARCH_URL  = f"{BASE_URL}/jobs/results/"
MAX_PAGES   = 15     # 20 jobs/page → 300 max
HTTP_TIMEOUT = 20

CATEGORIES = [
    "SOFTWARE_ENGINEERING",
    "DEVELOPER_RELATIONS",
    "TECHNICAL_INFRASTRUCTURE_ENGINEERING",
]


# ---------------------------------------------------------------------------
# UTC helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts) -> Optional[datetime]:
    """Convert Unix timestamp (seconds) to UTC-aware datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
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
        "Accept":          "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


# ---------------------------------------------------------------------------
# HTML fetch + ds:1 extraction
# ---------------------------------------------------------------------------

def _fetch_page(category: str, page: int, session: requests.Session) -> str:
    """Fetch one search results page, return raw HTML or '' on failure."""
    params = [
        ("category", category),
        ("location", "United States"),
        ("page",     str(page)),
    ]
    try:
        r = session.get(SEARCH_URL, params=params, timeout=HTTP_TIMEOUT)
        return r.text if r.ok else ""
    except Exception:
        return ""


def _extract_jobs(html: str) -> List[dict]:
    """
    Extract job list from the AF_initDataCallback ds:1 blob in the HTML.

    Returns a list of dicts with keys: id, title, apply_url, locations,
    published_ts, company.
    """
    # Find the ds:1 callback block
    # Find the start of the ds:1 data blob
    marker = "key: 'ds:1', hash: '"
    idx = html.find(marker)
    if idx == -1:
        return []
    # Find `data:` after the marker
    data_idx = html.find("data:", idx)
    if data_idx == -1:
        return []
    data_start = data_idx + 5  # skip 'data:'

    # Find the matching closing bracket for the data array
    # Walk forward counting brackets to find where the data ends
    depth = 0
    end = data_start
    in_str = False
    escape = False
    for i, ch in enumerate(html[data_start:], data_start):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in ('[', '{'):
            depth += 1
        elif ch in (']', '}'):
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    raw = html[data_start:end].strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    # data[0] is the list of job arrays
    job_arrays = data[0] if data and isinstance(data[0], list) else []

    results = []
    for job in job_arrays:
        if not isinstance(job, list) or len(job) < 13:
            continue
        try:
            job_id      = str(job[0]) if job[0] else ""
            title       = str(job[1]) if job[1] else ""
            apply_url   = str(job[2]) if job[2] else ""
            company     = str(job[7]) if len(job) > 7 and job[7] else "Google"

            # Locations: job[9] is a list of location arrays
            loc_list    = job[9] if len(job) > 9 and isinstance(job[9], list) else []
            locations   = "; ".join(
                str(loc[0]) for loc in loc_list
                if isinstance(loc, list) and loc and loc[0]
            )

            # Published date: job[13][0] (seconds)
            pub_entry   = job[13] if len(job) > 13 and isinstance(job[13], list) else []
            pub_ts      = pub_entry[0] if pub_entry else None

            if not job_id or not title:
                continue

            results.append({
                "id":           job_id,
                "title":        title,
                "apply_url":    apply_url,
                "locations":    locations,
                "published_ts": pub_ts,
                "company":      company,
            })
        except (IndexError, TypeError):
            continue

    return results


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
    company_name: str = "Google",
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
) -> List[Job]:
    """
    Scrape Google Careers for matching US software engineering roles.

    Fetches HTML pages for each category, extracts embedded job data from
    the AF_initDataCallback ds:1 blob, applies keyword + seniority + age
    filters. Dedupes by job ID across categories and pages.

    No slug, no API key, no JS rendering — plain GET requests only.

    Returns List[Job], empty on any failure, never raises.
    """
    try:
        session  = _make_session()
        cutoff   = _now() - timedelta(days=max_age_days) if max_age_days > 0 else None
        seen_ids: set = set()
        results: List[Job] = []

        for category in CATEGORIES:
            for page in range(1, MAX_PAGES + 1):
                html = _fetch_page(category, page, session)
                if not html:
                    break

                jobs = _extract_jobs(html)
                if not jobs:
                    break

                new_on_page = 0
                for item in jobs:
                    jid = item["id"]
                    if jid in seen_ids:
                        continue
                    seen_ids.add(jid)
                    new_on_page += 1

                    title = item["title"].strip()
                    if not title:
                        continue

                    if not _keyword_match(title, keywords):
                        continue

                    if not is_junior_enough(title):
                        continue

                    apply_url = item["apply_url"].strip()
                    if not apply_url:
                        continue

                    location    = item["locations"]
                    posted_dt   = _parse_ts(item["published_ts"])
                    posted_text = posted_dt.strftime("%Y-%m-%d") if posted_dt else ""

                    if cutoff is not None:
                        if posted_dt is None or posted_dt < cutoff:
                            continue

                    results.append(Job(
                        title=title,
                        company=item["company"],
                        link=apply_url,
                        location=location,
                        posted_text=posted_text,
                        posted_dt=posted_dt,
                    ))

                # If no new jobs on this page, stop paginating this category
                if new_on_page == 0:
                    break

                time.sleep(random.uniform(0.5, 1.0))

            time.sleep(random.uniform(0.5, 1.5))

        return results

    except Exception:
        return []
