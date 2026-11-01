"""SAP SuccessFactors Recruiting Marketing search adapter, verified with Wipro.

The career site's own search endpoint returns posting dates and all locations:
POST {base_url}/services/recruiting/v1/jobs

Use sortBy="date", not "recent" (which returned relevance-ordered results in
live checks). No job-description requests, browser automation, or DB access.
Other SuccessFactors tenants must be verified before adding them to config.
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import List, Optional
from urllib.parse import quote, unquote, urlparse

import requests

from scrapers import Job, is_junior_enough, is_location_allowed


logger = logging.getLogger(__name__)
HTTP_TIMEOUT = 20
DEFAULT_MAX_PAGES = 200
DEFAULT_MAX_RUNTIME_SECONDS = 120
REQUEST_DELAY = 0.2


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_text(value) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", value))).strip()


def _values(value) -> List[str]:
    values = value if isinstance(value, list) else [value]
    return list(dict.fromkeys(text for item in values if (text := _clean_text(item))))


def _parse_date(value) -> Optional[datetime]:
    value = _clean_text(value)
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _parse_search_item(item, base_url: str, locale: str) -> Optional[dict]:
    if not isinstance(item, dict) or not isinstance(item.get("response"), dict):
        return None
    source = item["response"]
    title = _clean_text(source.get("unifiedStandardTitle"))
    job_id = str(source.get("id") or "").strip()
    slug = _clean_text(source.get("unifiedUrlTitle") or source.get("urlTitle"))
    if not title or not job_id or not slug:
        return None

    # Keep all offices; do not zip city/state arrays (their orders can differ).
    offices = _values(source.get("jobLocationShort"))
    if not offices:
        offices = _values(source.get("sfstd_jobLocation_obj")) + _values(source.get("jobLocationState"))
    location_parts = dict.fromkeys(offices + _values(source.get("jobLocationCountry")))
    location = "; ".join(location_parts)
    posted_dt = _parse_date(source.get("unifiedStandardStart"))
    return {
        "job_id": job_id,
        "title": title,
        "link": (
            f"{base_url}/job/{quote(unquote(slug), safe='-._~')}/"
            f"{quote(job_id, safe='')}-{quote(locale, safe='_-')}"
        ),
        "location": location,
        "posted_dt": posted_dt,
        "posted_text": posted_dt.strftime("%Y-%m-%d") if posted_dt else "",
        "expires_dt": _parse_date(source.get("unifiedStandardEnd")),
    }


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "JobHunter/1.0 (job availability monitoring)",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session


def _search_page(session, base_url, locale, location, page, timeout):
    response = session.post(
        f"{base_url}/services/recruiting/v1/jobs",
        json={
            "keywords": "",  # Fetch once per scope; filter titles locally.
            "locale": locale,
            "location": location,
            "pageNumber": page,
            "sortBy": "date",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Search response is not an object")
    total = payload.get("totalJobs")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise ValueError("Search response has no valid totalJobs")
    rows = payload.get("jobSearchResult", [] if total == 0 else None)
    if not isinstance(rows, list) or (total == 0 and rows):
        raise ValueError("Search response has no valid jobSearchResult")
    return rows, total


def scrape(
    keywords: List[str],
    company_name: str,
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
    base_url: str = "",
    locale: str = "en_US",
    search_locations: Optional[List[str]] = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_runtime_seconds: float = DEFAULT_MAX_RUNTIME_SECONDS,
) -> List[Job]:
    """Return matching jobs, with bounded requests and observable partial scans.

    Source dates have day precision. Include the entire UTC cutoff date so a
    posting dated exactly N days ago isn't lost due to an invented time-of-day.
    Query US first, then worldwide, to retain explicitly labelled foreign remote
    roles without sacrificing US coverage when the shared runtime budget expires.
    """
    results: List[Job] = []
    started = time.monotonic()
    pages_fetched = 0
    try:
        base_url = base_url.strip().rstrip("/")
        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise ValueError("An absolute careers base_url is required")
        max_pages = int(max_pages)
        runtime = float(max_runtime_seconds)
        if max_pages <= 0 or not 0 < runtime <= 3600:
            raise ValueError("max_pages must be positive and runtime must be in (0, 3600]")
        deadline = started + runtime
        now = _now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = today - timedelta(days=max_age_days) if max_age_days > 0 else None
        scopes = ["United States", ""] if search_locations is None else search_locations
        scopes = list(dict.fromkeys(str(scope).strip() for scope in scopes)) or [""]
        terms = [term.lower() for term in keywords if term]
        seen_ids = set()

        with _make_session() as session:
            for scope in scopes:
                scope_label = scope or "worldwide"
                logger.info("%s: SuccessFactors scanning %s (posting cutoff %s)",
                            company_name, scope_label, cutoff.date() if cutoff else "none")
                previous_date = None
                ordered = True
                fingerprints = set()
                rows_fetched = 0
                for page in range(max_pages):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        logger.warning("%s: SuccessFactors runtime limit reached; coverage is partial (%s)",
                                       company_name, scope_label)
                        return results
                    if pages_fetched:
                        time.sleep(min(REQUEST_DELAY, remaining))
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        logger.warning("%s: SuccessFactors runtime limit reached; coverage is partial (%s)",
                                       company_name, scope_label)
                        return results

                    rows, total = _search_page(
                        session, base_url, locale, scope, page, min(HTTP_TIMEOUT, remaining),
                    )
                    pages_fetched += 1
                    if not rows:
                        if rows_fetched < total:
                            logger.warning("%s: empty SuccessFactors page before totalJobs; coverage is partial (%s)",
                                           company_name, scope_label)
                        break

                    parsed_rows = [_parse_search_item(row, base_url, locale) for row in rows]
                    fingerprint = frozenset(row["job_id"] for row in parsed_rows if row)
                    if fingerprint and fingerprint in fingerprints:
                        logger.warning("%s: repeated SuccessFactors page; coverage is partial (%s)",
                                       company_name, scope_label)
                        break
                    fingerprints.add(fingerprint)
                    rows_fetched += len(rows)
                    page_dates = []
                    for row in parsed_rows:
                        posted = row["posted_dt"] if row else None
                        page_dates.append(posted)
                        if posted is None or (previous_date is not None and posted > previous_date):
                            if ordered:
                                logger.warning("%s: SuccessFactors dates missing/out of order; disabling age early-stop (%s)",
                                               company_name, scope_label)
                            ordered = False
                        if posted is not None:
                            previous_date = posted
                        if row is None or posted is None or posted > today:
                            continue
                        if cutoff is not None and posted < cutoff:
                            continue
                        if row["expires_dt"] is not None and row["expires_dt"] < today:
                            continue
                        title = row["title"]
                        if terms and not any(term in title.lower() for term in terms):
                            continue
                        if not is_junior_enough(title) or not is_location_allowed(row["location"], locations or []):
                            continue
                        if row["job_id"] in seen_ids:
                            continue
                        seen_ids.add(row["job_id"])
                        results.append(Job(
                            title=title,
                            company=company_name,
                            link=row["link"],
                            location=row["location"],
                            posted_text=row["posted_text"],
                            posted_dt=posted,
                        ))

                    if rows_fetched >= total:
                        break
                    if cutoff is not None and ordered and all(date < cutoff for date in page_dates):
                        break
                else:
                    logger.warning("%s: SuccessFactors max_pages=%d reached; coverage is partial (%s)",
                                   company_name, max_pages, scope_label)
                logger.info("%s: SuccessFactors checked %d rows in %s scope",
                            company_name, rows_fetched, scope_label)

    except Exception:
        logger.exception("%s: SuccessFactors search failed; returning %d matches from partial coverage",
                         company_name, len(results))
    finally:
        logger.info("%s: SuccessFactors fetched %d pages in %.1fs; %d matching jobs",
                    company_name, pages_fetched, time.monotonic() - started, len(results))
    return results
