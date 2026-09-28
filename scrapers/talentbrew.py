"""
scrapers/talentbrew.py

Scrapes TalentBrew/Radancy career sites that render search results as HTML.

McKesson uses this platform. Its search page contains server-rendered result
rows with title, link, stable job id, location, and posted date. That makes it
much cleaner than custom sites that omit dates.

Expected result row shapes:
  <a class="search-results__job-title-link"
     href="/en/job/irving/title/733/100183311136"
     data-job-id="100183311136">Title</a>
  <span class="search-results__job-location">Irving, TX</span>
  <span class="search-results__job-date-posted">09/04/2026</span>

Newer Radancy/TalentBrew sites often render rows as:
  <section id="search-results-list">
    <li>
      <a href="/job/city/title/117/1001" data-job-id="1001">
        <h2>Title</h2>
        <span class="job-location">City, ST</span>
        <span class="job-date-posted">09/04/2026</span>
      </a>
    </li>
  </section>

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
DEFAULT_DETAIL_FETCH_LIMIT = 20


# ---------------------------------------------------------------------------
# UTC/date helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_tb_date(date_str: str) -> Optional[datetime]:
    """
    Parse TalentBrew's visible posted date into UTC midnight.

    Returns None if parsing fails.
    """
    if not date_str:
        return None

    value = _clean_text(str(date_str))
    value = re.sub(r"(?i)\bdate\s+posted:?\b", "", value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%-m-%-d"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            continue

    match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", value)
    if match:
        try:
            parsed = datetime.strptime(match.group(1), "%m/%d/%Y")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    match = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2})\b", value)
    if match:
        try:
            parsed = datetime.strptime(match.group(1), "%Y-%m-%d")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

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
    seen_keys = set()

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

        key = job_id or link
        if key in seen_keys:
            continue
        seen_keys.add(key)

        jobs.append({
            "title": title,
            "job_id": job_id,
            "link": link,
            "location": _with_location_label(location, location_label),
            "posted_text": posted_text,
            "posted_dt": _parse_tb_date(posted_text),
        })

    for row in soup.select("#search-results-list li"):
        link_node = row.select_one("a[data-job-id][href]")
        if not link_node:
            continue

        title_node = link_node.select_one("h2")
        title = _clean_text(
            title_node.get_text(" ", strip=True)
            if title_node else link_node.get_text(" ", strip=True)
        )
        link = urljoin(base_url.rstrip("/") + "/", link_node.get("href", ""))
        job_id = _clean_text(link_node.get("data-job-id", ""))
        if not title or not link:
            continue

        key = job_id or link
        if key in seen_keys:
            continue
        seen_keys.add(key)

        location_nodes = row.select(".job-location")
        location = "; ".join(
            _clean_text(node.get_text(" ", strip=True))
            for node in location_nodes
            if _clean_text(node.get_text(" ", strip=True))
        )

        worksetting_node = row.select_one(".job-worksetting")
        worksetting = _clean_text(worksetting_node.get_text(" ", strip=True)) if worksetting_node else ""
        if worksetting:
            location = _with_location_label(location, worksetting)

        date_node = row.select_one(".search-results__job-date-posted, .job-date-posted, .job-date")
        posted_text = _clean_text(date_node.get_text(" ", strip=True)) if date_node else ""

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
    search_terms: Optional[List[str] | str] = None,
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
    terms = _normalise_location_params(search_terms, "")
    if not terms:
        terms = [""]

    all_jobs: List[dict] = []
    seen = set()

    for search_term in terms:
        term_params = dict(query_params)
        if search_term:
            term_params["k"] = search_term

        for location_param in loc_params:
            location_param = str(location_param).strip()
            location_label = labels.get(location_param, "")

            for page in range(1, max_pages + 1):
                html = _fetch_page(
                    session=session,
                    base_url=base_url,
                    search_path=search_path,
                    query_params=term_params,
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


def _fetch_detail_posted_date(session: requests.Session, link: str) -> tuple[str, Optional[datetime]]:
    """Fetch a TalentBrew detail page and extract a posted date if present."""
    if not link:
        return "", None

    try:
        r = session.get(link, timeout=HTTP_TIMEOUT)
        if not r.ok:
            return "", None
    except Exception:
        return "", None

    soup = BeautifulSoup(r.text or "", "lxml")

    for script in soup.select("script[type='application/ld+json']"):
        text = script.string or script.get_text(" ", strip=True)
        match = re.search(r'"datePosted"\s*:\s*"([^"]+)"', text)
        if match:
            posted_text = match.group(1)
            return posted_text, _parse_tb_date(posted_text)

    date_node = soup.select_one(".job-date")
    if date_node:
        posted_text = _clean_text(date_node.get_text(" ", strip=True))
        return posted_text, _parse_tb_date(posted_text)

    text = soup.get_text(" ", strip=True)
    match = re.search(r"(?i)\bdate\s+posted:?\s*(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2})", text)
    if match:
        posted_text = match.group(1)
        return posted_text, _parse_tb_date(posted_text)

    return "", None


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
    search_terms: Optional[List[str] | str] = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    detail_fetch_limit: int = DEFAULT_DETAIL_FETCH_LIMIT,
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
            search_terms=search_terms,
            max_pages=max_pages,
        )

        cutoff = _now() - timedelta(days=max_age_days) if max_age_days > 0 else None
        results: List[Job] = []
        detail_fetches = 0

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
            if cutoff is not None and posted_dt is None and detail_fetches < detail_fetch_limit:
                detail_fetches += 1
                fetched_text, fetched_dt = _fetch_detail_posted_date(session, item.get("link", ""))
                if fetched_dt is not None:
                    posted_text = fetched_text
                    posted_dt = fetched_dt

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
