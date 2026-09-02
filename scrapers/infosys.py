"""
scrapers/infosys.py

Scrapes Infosys' public Digital Careers pages.

This is NOT Greenhouse/Ashby/Lever/etc.; Infosys appears to run a custom
Digital Careers frontend. The listing pages are server-rendered HTML and can
be paginated with `page` / `per_page`.

Important limitation:
  Infosys pages do not expose a reliable posted/published timestamp in the
  visible listing/detail HTML. Because of that, this scraper does not enforce
  max_age_days. It returns currently open matching jobs and relies on the
  existing SQLite seen_jobs dedup to email only newly discovered req IDs after
  the initial baseline is recorded.

Search endpoint:
  GET https://digitalcareers.infosys.com/infosys/global-careers
      ?location=USA&page={page}&per_page={per_page}

Job detail endpoint:
  https://digitalcareers.infosys.com/global-careers/company-job/description/reqid/{REQID}

HOW TO CUSTOMISE:
  - add/remove role keywords → config/config-infosys.yaml keywords/extra_keywords
  - change location filters  → config/config-infosys.yaml locations/extra_locations
  - cap pagination/runtime   → config/config-infosys.yaml max_pages / per_page
  - pause Infosys            → config/config-infosys.yaml active: false
"""

import random
import re
import time
from html import unescape
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from scrapers import Job, is_junior_enough, is_location_allowed

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://digitalcareers.infosys.com"
SEARCH_URL = f"{BASE_URL}/infosys/global-careers"
HTTP_TIMEOUT = 20
DEFAULT_PER_PAGE = 100
DEFAULT_MAX_PAGES = 3
MAX_PER_PAGE = 100


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
    """Return True if location matches the configured allowed terms."""
    return is_location_allowed(location, allowed)


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
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _clean_text(value: str) -> str:
    """Collapse HTML-ish whitespace and non-breaking spaces."""
    value = unescape(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def _absolute_url(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return f"{BASE_URL}{href}"
    return f"{BASE_URL}/{href}"


def _extract_reqid(link: str) -> str:
    match = re.search(r"/reqid/([^/?#]+)", link or "", re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_location(card: BeautifulSoup) -> str:
    location_node = card.select_one(".job-location")
    if not location_node:
        return ""

    parts = []
    for node in location_node.select(".location-inline"):
        text = _clean_text(node.get_text(" ", strip=True))
        if not text or re.fullmatch(r"[-,]+", text):
            continue
        parts.append(text)

    return ", ".join(parts)


def _parse_job_cards(html: str) -> List[dict]:
    """
    Parse one Infosys listing page into raw job dicts.

    The site renders each job as:
      <a href=".../company-job/description/reqid/151838BR" class="job">
        <div class="job-title" data-title="Cloud Engineer">...</div>
        <div class="job-location">Richardson, TX - USA</div>
        <div class="js-job-reqid">151838BR</div>
      </a>
    """
    soup = BeautifulSoup(html or "", "lxml")
    jobs = []

    for card in soup.select("a.job[href*='company-job/description/reqid/']"):
        href = _absolute_url(card.get("href", ""))
        if not href:
            continue

        title_node = card.select_one(".job-title")
        title = ""
        if title_node:
            title = _clean_text(title_node.get("data-title") or title_node.get_text(" ", strip=True))
        if not title:
            continue

        reqid_node = card.select_one(".js-job-reqid")
        reqid = _clean_text(reqid_node.get_text(" ", strip=True)) if reqid_node else ""
        if not reqid:
            reqid = _extract_reqid(href)

        location = _parse_location(card)

        jobs.append({
            "title": title,
            "location": location,
            "reqid": reqid,
            "link": href,
        })

    return jobs


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def _fetch_page(
    session: requests.Session,
    page: int,
    per_page: int,
    location_param: str,
) -> str:
    """Fetch one Infosys listing page. Returns HTML text or '' on failure."""
    try:
        r = session.get(
            SEARCH_URL,
            params={
                "location": location_param,
                "page": page,
                "per_page": per_page,
            },
            timeout=HTTP_TIMEOUT,
        )
        if not r.ok:
            return ""
        return r.text or ""
    except Exception:
        return ""


def _fetch_jobs(
    session: requests.Session,
    max_pages: int = DEFAULT_MAX_PAGES,
    per_page: int = DEFAULT_PER_PAGE,
    location_param: str = "USA",
) -> List[dict]:
    """
    Fetch Infosys listing pages and return raw parsed job dicts.

    Pagination is capped by max_pages to keep runtime predictable. Stops early
    if a page returns no cards.
    """
    max_pages = max(1, int(max_pages or DEFAULT_MAX_PAGES))
    per_page = max(1, min(int(per_page or DEFAULT_PER_PAGE), MAX_PER_PAGE))
    location_param = (location_param or "USA").strip()

    all_jobs: List[dict] = []
    seen_links = set()

    for page in range(1, max_pages + 1):
        html = _fetch_page(session, page, per_page, location_param)
        if not html:
            break

        page_jobs = _parse_job_cards(html)
        if not page_jobs:
            break

        for item in page_jobs:
            link = item.get("link", "")
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            all_jobs.append(item)

        if len(page_jobs) < per_page:
            break

        time.sleep(random.uniform(0.3, 0.6))

    return all_jobs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape(
    slug: str,
    keywords: List[str],
    company_name: str,
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
    max_pages: int = DEFAULT_MAX_PAGES,
    per_page: int = DEFAULT_PER_PAGE,
    location_param: str = "USA",
) -> List[Job]:
    """
    Scrape Infosys Digital Careers and return matching open jobs.

    `slug` is accepted for consistency with the poller/config model but is not
    used by the Infosys site; the tenant is fixed by SEARCH_URL.

    Filters applied:
      1. Keyword match
      2. Seniority filter
      3. Location filter

    Age filter note:
      max_age_days is intentionally ignored because Infosys does not expose a
      reliable posted date. Dedup by reqid/link handles future "new job" alerts.
    """
    del slug, max_age_days  # accepted for config/router consistency

    loc = [l.strip() for l in (locations or []) if l.strip()]
    results: List[Job] = []

    try:
        session = _make_session()
        raw_jobs = _fetch_jobs(
            session=session,
            max_pages=max_pages,
            per_page=per_page,
            location_param=location_param,
        )

        for item in raw_jobs:
            title = (item.get("title") or "").strip()
            if not title:
                continue

            if not _keyword_match(title, keywords):
                continue

            if not is_junior_enough(title):
                continue

            location = (item.get("location") or "").strip()
            if not _location_match(location, loc):
                continue

            link = (item.get("link") or "").strip()
            if not link:
                continue

            reqid = (item.get("reqid") or _extract_reqid(link)).strip()
            posted_text = f"reqid {reqid}" if reqid else ""

            results.append(Job(
                title=title,
                company=company_name,
                link=link,
                location=location,
                posted_text=posted_text,
                posted_dt=None,
            ))

        time.sleep(random.uniform(0.5, 1.0))
        return results

    except Exception:
        return []
