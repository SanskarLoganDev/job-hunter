"""
scrapers/talentbrew.py

Scrapes TalentBrew/Radancy career sites that render search results as HTML.

McKesson uses this platform. Its search page contains server-rendered result
rows with title, link, stable job id, location, and posted date. That makes it
much cleaner than custom sites that omit dates.

Expected result row shape:
  <a class="search-results__job-title-link"
     href="/en/job/irving/title/733/100183311136"
     data-job-id="100183311136">Title</a>
  <span class="search-results__job-location">Irving, TX</span>
  <span class="search-results__job-date-posted">09/04/2026</span>

Pagination:
  TalentBrew uses `p=1`, `p=2`, ... for result pages. Page 1 also works with
  no `p`, but using `p=1` consistently keeps the fetcher simple.

Location facets:
  Some sites encode country/remote filters as numeric `alrpm` values. The
  scraper supports multiple `location_params` and optional
  `location_param_labels` so a vague row like "Multiple" can become
  "Multiple; United States" or "Multiple; Remote" based on the query used.
"""

import random
import re
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers import Job, is_junior_enough, is_location_allowed

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HTTP_TIMEOUT = 20
DEFAULT_MAX_PAGES = 5


# ---------------------------------------------------------------------------
# UTC/date helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_tb_date(date_str: str) -> Optional[datetime]:
    """
    Parse TalentBrew's MM/DD/YYYY posted date into UTC midnight.

    Returns None if parsing fails.
    """
    if not date_str:
        return None
    try:
        parsed = datetime.strptime(date_str.strip(), "%m/%d/%Y")
        return parsed.replace(tzinfo=timezone.utc)
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
    value = unescape(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def _with_location_label(location: str, label: str) -> str:
    location = _clean_text(location)
    label = _clean_text(label)
    if not label:
        return location
    if not location:
        return label
    if label.lower() in location.lower():
        return location
    return f"{location}; {label}"


def _parse_job_rows(html: str, base_url: str, location_label: str = "") -> List[dict]:
    """Parse one TalentBrew search-results page into raw job dicts."""
    soup = BeautifulSoup(html or "", "lxml")
    jobs = []

    for link_node in soup.select("a.search-results__job-title-link"):
        title = _clean_text(link_node.get_text(" ", strip=True))
        link = urljoin(base_url.rstrip("/") + "/", link_node.get("href", ""))
        job_id = _clean_text(link_node.get("data-job-id", ""))
        if not title or not link:
            continue

        row = link_node.find_parent("li")
        location = ""
        posted_text = ""
        if row:
            location_node = row.select_one(".search-results__job-location")
            date_node = row.select_one(".search-results__job-date-posted")
            if location_node:
                location = _clean_text(location_node.get_text(" ", strip=True))
            if date_node:
                posted_text = _clean_text(date_node.get_text(" ", strip=True))

        jobs.append({
            "title": title,
            "job_id": job_id,
            "link": link,
            "location": _with_location_label(location, location_label),
            "posted_text": posted_text,
            "posted_dt": _parse_tb_date(posted_text),
        })

    return jobs


def _normalise_location_params(
    location_params: Optional[List[str] | str],
    fallback: str,
) -> List[str]:
    if location_params is None:
        return [fallback]
    if isinstance(location_params, str):
        return [location_params]
    return [str(value) for value in location_params if str(value).strip()]


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def _fetch_page(
    session: requests.Session,
    base_url: str,
    search_path: str,
    query_params: Optional[dict],
    page: int,
    location_param: str,
) -> str:
    """Fetch one TalentBrew listing page. Returns HTML text or '' on failure."""
    url = urljoin(base_url.rstrip("/") + "/", search_path.lstrip("/"))
    params = dict(query_params or {})
    params["p"] = page
    if location_param:
        params["alrpm"] = location_param

    try:
        r = session.get(url, params=params, timeout=HTTP_TIMEOUT)
        if not r.ok:
            return ""
        return r.text or ""
    except Exception:
        return ""


def _fetch_jobs(
    session: requests.Session,
    base_url: str,
    search_path: str,
    query_params: Optional[dict] = None,
    location_params: Optional[List[str] | str] = None,
    location_param_labels: Optional[dict] = None,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> List[dict]:
    """
    Fetch TalentBrew listing pages and return raw parsed job dicts.

    Dedupe by job id when available, otherwise by URL. Pagination is capped by
    max_pages so a large board does not stretch the scheduled poller run.
    """
    max_pages = max(1, int(max_pages or DEFAULT_MAX_PAGES))
    query_params = dict(query_params or {})
    fallback_location = str(query_params.get("alrpm", "ALL"))
    loc_params = _normalise_location_params(location_params, fallback_location)
    labels = {str(k): str(v) for k, v in (location_param_labels or {}).items()}

    all_jobs: List[dict] = []
    seen = set()

    for location_param in loc_params:
        location_param = str(location_param).strip()
        location_label = labels.get(location_param, "")

        for page in range(1, max_pages + 1):
            html = _fetch_page(
                session=session,
                base_url=base_url,
                search_path=search_path,
                query_params=query_params,
                page=page,
                location_param=location_param,
            )
            if not html:
                break

            page_jobs = _parse_job_rows(html, base_url, location_label)
            if not page_jobs:
                break

            before = len(all_jobs)
            for item in page_jobs:
                key = item.get("job_id") or item.get("link")
                if not key or key in seen:
                    continue
                seen.add(key)
                all_jobs.append(item)

            if len(all_jobs) == before:
                break

            time.sleep(random.uniform(0.3, 0.6))

    return all_jobs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape(
    keywords: List[str],
    company_name: str,
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
    base_url: str = "",
    search_path: str = "/en/search-jobs",
    query_params: Optional[dict] = None,
    location_params: Optional[List[str] | str] = None,
    location_param_labels: Optional[dict] = None,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> List[Job]:
    """
    Scrape a TalentBrew/Radancy careers site and return matching jobs.

    Filters applied:
      1. Keyword match
      2. Seniority filter
      3. Location filter
      4. Age filter using the listing page's MM/DD/YYYY posted date
    """
    if not base_url:
        return []

    loc = [l.strip() for l in (locations or []) if l.strip()]

    try:
        session = _make_session()
        raw_jobs = _fetch_jobs(
            session=session,
            base_url=base_url,
            search_path=search_path,
            query_params=query_params,
            location_params=location_params,
            location_param_labels=location_param_labels,
            max_pages=max_pages,
        )

        cutoff = _now() - timedelta(days=max_age_days) if max_age_days > 0 else None
        results: List[Job] = []

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

            posted_dt = item.get("posted_dt")
            posted_text = item.get("posted_text") or ""
            if cutoff is not None:
                if posted_dt is None or posted_dt < cutoff:
                    continue

            link = (item.get("link") or "").strip()
            if not link:
                continue

            results.append(Job(
                title=title,
                company=company_name,
                link=link,
                location=location,
                posted_text=posted_text,
                posted_dt=posted_dt,
            ))

        time.sleep(random.uniform(0.5, 1.0))
        return results

    except Exception:
        return []
