"""
scrapers/amazon.py

Scrapes amazon.jobs for software / engineering roles.

Strategy (in order):
  1. Hit the undocumented search.json endpoint — fastest, cleanest data.
  2. Fall back to HTML parsing of the category and search pages.
  3. Enrich missing posted dates by fetching individual job detail pages.
  4. Filter by seniority — excludes senior/staff/principal/lead etc.
  5. Filter by location (USA only by default).
  6. Filter by max_age_days.

Returns List[Job] — always, even on total failure (returns []).

HOW TO CUSTOMISE (no code changes needed):
  - add/remove role keywords    → config.yaml  keywords
  - change location filters     → config.yaml  locations
  - change the age cutoff       → config.yaml  max_age_days
  - pause Amazon                → config.yaml  active: false
  - seniority exclusions        → scrapers/__init__.py  _SENIOR_TERMS
"""

import json
import random
import time
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers import Job, is_junior_enough

# ---------------------------------------------------------------------------
# UTC helper
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AMAZON_BASE  = "https://www.amazon.jobs/en/"
AMAZON_ROOT  = "https://www.amazon.jobs"
HTTP_TIMEOUT = 30
JOB_PATH_RE  = re.compile(r"^(/en)?/jobs/")

MONTH_INDEX = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3,   "apr": 4, "april": 4,
    "may": 5,               "jun": 6, "june": 6,
    "jul": 7, "july": 7,    "aug": 8, "august": 8,
    "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

DATE_RE          = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
ISO_DATE_RE      = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
MONTH_NAME_RE    = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+(\d{1,2}),\s*(\d{4})\b",
    re.I,
)
RELATIVE_RE      = re.compile(
    r"(\d+)\s+(hour|hours|day|days|week|weeks|month|months)\s+ago", re.I
)
UPDATED_LABEL_RE = re.compile(
    r"(Updated|Posted)\s*:?\s*(?P<date>"
    r"(?:\d{4}-\d{2}-\d{2})|(?:\d{1,2}/\d{1,2}/\d{4})|"
    r"(?:[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}))",
    re.I,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(text: str) -> tuple[Optional[str], Optional[datetime]]:
    if not text:
        return None, None

    m = ISO_DATE_RE.search(text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return m.group(1), dt
        except ValueError:
            pass

    m = MONTH_NAME_RE.search(text)
    if m:
        try:
            mon = MONTH_INDEX[m.group(1).lower()]
            dt = datetime(int(m.group(3)), mon, int(m.group(2)), tzinfo=timezone.utc)
            return m.group(0), dt
        except (KeyError, ValueError):
            pass

    m = DATE_RE.search(text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%m/%d/%Y").replace(tzinfo=timezone.utc)
            return m.group(1), dt
        except ValueError:
            pass

    m = RELATIVE_RE.search(text)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "hour":  timedelta(hours=n),    "hours":  timedelta(hours=n),
            "day":   timedelta(days=n),     "days":   timedelta(days=n),
            "week":  timedelta(weeks=n),    "weeks":  timedelta(weeks=n),
            "month": timedelta(days=30*n),  "months": timedelta(days=30*n),
        }.get(unit)
        if delta:
            return m.group(0), _now() - delta

    return None, None


def _normalize_link(href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http"):
        return href if ("amazon.jobs" in href and "/jobs/" in href) else ""
    return urljoin(AMAZON_ROOT, href) if JOB_PATH_RE.search(href) else ""


def _location_allowed(location: str, allowed: List[str]) -> bool:
    if not allowed:
        return True
    loc_lower = location.lower()
    return any(term.lower() in loc_lower for term in allowed)


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "application/json;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": AMAZON_BASE,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    try:
        s.get(AMAZON_BASE, timeout=HTTP_TIMEOUT)
        time.sleep(random.uniform(0.5, 1.2))
    except Exception:
        pass
    return s


# ---------------------------------------------------------------------------
# Strategy 1: JSON API
# ---------------------------------------------------------------------------

_JSON_CANDIDATES = [
    ("https://www.amazon.jobs/en/search.json",
     [("result_limit", "100"), ("offset", "0"), ("category[]", "Software Development")]),
    ("https://www.amazon.jobs/en/search.json",
     [("result_limit", "100"), ("offset", "0"), ("job_category[]", "Software Development")]),
    ("https://www.amazon.jobs/en/search.json",
     [("result_limit", "100"), ("offset", "0"), ("query", "software engineer")]),
]


def _try_json(
    session: requests.Session,
    keywords: List[str],
    locations: List[str],
) -> List[dict]:
    for url, params in _JSON_CANDIDATES:
        try:
            r = session.get(url, params=params, timeout=HTTP_TIMEOUT)
            if not r.ok:
                continue
            data = r.json()
        except Exception:
            continue

        candidates = []
        if isinstance(data, dict):
            for key in ("jobs", "search_results", "results", "hits", "items"):
                if isinstance(data.get(key), list):
                    candidates.append(data[key])
            if not candidates:
                for v in data.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        candidates.append(v)

        raw = []
        for lst in candidates:
            for item in lst:
                title = (item.get("title") or item.get("job_title") or "").strip()
                if not title:
                    continue

                # Keyword filter
                if keywords and not any(k in title.lower() for k in keywords):
                    continue

                # Seniority filter — excludes senior/staff/principal/lead etc.
                if not is_junior_enough(title):
                    continue

                href = (
                    item.get("job_path") or item.get("absolute_url") or
                    item.get("apply_url") or item.get("url_next_step") or ""
                ).strip()
                link = _normalize_link(href)
                if not link:
                    continue

                location = (
                    item.get("location") or item.get("normalized_location") or
                    item.get("city") or ""
                )
                if not _location_allowed(location, locations):
                    continue

                posted_raw = (
                    item.get("posted_date") or item.get("posting_date") or
                    item.get("posted_at") or ""
                )
                posted_txt, posted_dt = _parse_date(str(posted_raw))

                raw.append({
                    "title":       title,
                    "link":        link,
                    "location":    location,
                    "posted_text": posted_txt or str(posted_raw),
                    "posted_dt":   posted_dt,
                })

        if raw:
            seen = {}
            for j in raw:
                seen[(j["title"], j["link"])] = j
            return list(seen.values())

    return []


# ---------------------------------------------------------------------------
# Strategy 2: HTML fallback
# ---------------------------------------------------------------------------

def _extract_jobs_from_html(
    html: str,
    keywords: List[str],
    locations: List[str],
) -> List[dict]:
    soup = BeautifulSoup(html, "lxml")
    raw = []

    for a in soup.find_all("a", href=True):
        link = _normalize_link(a["href"])
        if not link:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        if keywords and not any(k in title.lower() for k in keywords):
            continue

        # Seniority filter
        if not is_junior_enough(title):
            continue

        parent = a.find_parent()
        block = parent.get_text(" ", strip=True) if parent else title

        known_us_terms = [
            "United States", "US", "USA", "Remote",
            "Seattle", "New York", "Austin", "San Francisco",
            "Boston", "Chicago", "Dallas", "Atlanta", "Arlington",
            "Bellevue", "Redmond", "Sunnyvale", "Santa Clara",
            "Washington", "Virginia", "New Jersey",
        ]
        location = next((kw for kw in known_us_terms if kw in block), "")
        if not _location_allowed(location, locations):
            continue

        posted_txt, posted_dt = _parse_date(block)
        raw.append({
            "title":       title,
            "link":        link,
            "location":    location,
            "posted_text": posted_txt or "",
            "posted_dt":   posted_dt,
        })

    seen = {}
    for j in raw:
        seen[(j["title"], j["link"])] = j
    return list(seen.values())


def _try_html(
    session: requests.Session,
    keywords: List[str],
    locations: List[str],
) -> List[dict]:
    raw = []
    urls = [
        urljoin(AMAZON_BASE, "job_categories/software-development"),
        urljoin(AMAZON_BASE, "search") + "?category=Software+Development",
        urljoin(AMAZON_BASE, "search") + "?query=software+engineer",
    ]
    for url in urls:
        try:
            r = session.get(url, timeout=HTTP_TIMEOUT)
            if r.ok:
                raw.extend(_extract_jobs_from_html(r.text, keywords, locations))
        except Exception:
            pass
    seen = {}
    for j in raw:
        seen[(j["title"], j["link"])] = j
    return list(seen.values())


# ---------------------------------------------------------------------------
# Strategy 3: Date enrichment
# ---------------------------------------------------------------------------

def _enrich_dates(raw: List[dict], session: requests.Session, limit: int) -> None:
    fetched = 0
    for j in raw:
        if j.get("posted_dt") or fetched >= limit:
            continue
        link = j.get("link")
        if not link:
            continue
        try:
            r = session.get(link, timeout=HTTP_TIMEOUT)
            if not r.ok:
                continue
            soup = BeautifulSoup(r.text, "lxml")

            found = False
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or script.text or "{}")
                except Exception:
                    continue
                for obj in (data if isinstance(data, list) else [data]):
                    if not isinstance(obj, dict):
                        continue
                    for key in ("datePosted", "dateModified", "datePublished"):
                        if key in obj:
                            txt, dt = _parse_date(str(obj[key]))
                            if dt:
                                j["posted_dt"]   = dt
                                j["posted_text"] = txt or str(obj[key])
                                found = True
                                break
                    if found:
                        break
                if found:
                    break

            if not j.get("posted_dt"):
                for prop in ("article:published_time", "article:modified_time",
                             "og:updated_time"):
                    tag = soup.find("meta", attrs={"property": prop})
                    if tag and tag.get("content"):
                        txt, dt = _parse_date(tag["content"])
                        if dt:
                            j["posted_dt"]   = dt
                            j["posted_text"] = txt or tag["content"]
                            break

            if not j.get("posted_dt"):
                m = UPDATED_LABEL_RE.search(soup.get_text(" ", strip=True))
                if m:
                    txt, dt = _parse_date(m.group("date"))
                    if dt:
                        j["posted_dt"]   = dt
                        j["posted_text"] = f"{m.group(1).title()}: {m.group('date')}"

        except Exception:
            pass

        fetched += 1
        time.sleep(random.uniform(0.3, 0.8))


# ---------------------------------------------------------------------------
# Age filter
# ---------------------------------------------------------------------------

def _filter_age(raw: List[dict], max_age_days: int) -> List[dict]:
    if max_age_days == 0:
        return raw
    cutoff = _now() - timedelta(days=max_age_days)
    fresh = []
    for j in raw:
        dt = j.get("posted_dt")
        if not dt:
            _, dt = _parse_date(j.get("posted_text", ""))
        if dt and dt >= cutoff:
            fresh.append(j)
    return fresh


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape(
    keywords: List[str],
    max_age_days: int = 2,
    detail_fetch_limit: int = 30,
    company_name: str = "Amazon",
    locations: Optional[List[str]] = None,
) -> List[Job]:
    kw  = [k.strip().lower() for k in keywords        if k.strip()]
    loc = [l.strip()         for l in (locations or []) if l.strip()]

    try:
        session = _make_session()

        raw = _try_json(session, kw, loc)
        if not raw:
            raw = _try_html(session, kw, loc)

        if detail_fetch_limit > 0:
            _enrich_dates(raw, session, detail_fetch_limit)

        raw = _filter_age(raw, max_age_days)

        return [
            Job(
                title=j["title"],
                company=company_name,
                link=j["link"],
                location=j.get("location", ""),
                posted_text=j.get("posted_text", ""),
                posted_dt=j.get("posted_dt"),
            )
            for j in raw
        ]

    except Exception:
        return []
