"""
scrapers/zwayam.py

Scrapes Zwayam/Openings.co career sites.

Impetus uses this platform at:
  https://impetus.openings.co/impetus

The public job pages are Angular shells, but the site uses public Zwayam APIs:
  - POST https://public.zwayam.com/jobs/search
  - POST https://public.zwayam.com/jobs-service/v1/jobs/careersite

Search expects multipart form data with a base64 company id. Detail expects
JSON with the numeric company id.
"""

import base64
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from scrapers import Job, is_junior_enough, is_location_allowed


API_BASE = "https://public.zwayam.com"
HTTP_TIMEOUT = 20
DEFAULT_MAX_PAGES = 3
PAGE_SIZE = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _keyword_match(title: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    title_lower = title.lower()
    return any(k.lower() in title_lower for k in keywords)


def _location_match(location: str, allowed: List[str]) -> bool:
    return is_location_allowed(location, allowed)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _company_id_b64(company_id: int | str) -> str:
    value = str(company_id or "").strip()
    if not value:
        return ""
    try:
        base64.b64decode(value, validate=True)
        return value
    except Exception:
        return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _parse_epoch_ms(value) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _format_posted(dt: Optional[datetime], fallback: str = "") -> str:
    if dt is not None:
        return dt.strftime("%m/%d/%Y")
    return fallback


def _make_session(tenant_group_id: str = "") -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    if tenant_group_id:
        s.headers["TenantGroupId"] = tenant_group_id
    return s


def _build_job_link(domain: str, path_prefix: str, job_url: str, job_id: str) -> str:
    domain = domain.strip().rstrip("/")
    prefix = path_prefix.strip().strip("/")
    job_url = str(job_url or "").strip()
    job_id = str(job_id or "").strip()
    if not domain or not job_url:
        return ""
    path = f"/{prefix}/jobview/{job_url}" if prefix else f"/jobview/{job_url}"
    suffix = f"?id={job_id}" if job_id else ""
    return f"https://{domain}{path}{suffix}"


def _extract_source(item: dict) -> dict:
    return item.get("_source") if isinstance(item.get("_source"), dict) else item


def _parse_search_item(item: dict, domain: str, path_prefix: str) -> dict:
    source = _extract_source(item or {})
    title = _clean_text(source.get("jobTitle") or source.get("title"))
    job_id = _clean_text(source.get("id") or source.get("jobId"))
    job_url = _clean_text(source.get("jobUrl"))
    location = _clean_text(source.get("location"))
    posted_dt = _parse_epoch_ms(source.get("createdDate"))
    job_code = _clean_text(source.get("jobCode") or source.get("referenceNumber"))

    return {
        "title": title,
        "job_id": job_id,
        "job_url": job_url,
        "location": location,
        "posted_text": _format_posted(posted_dt, f"jobCode {job_code}" if job_code else ""),
        "posted_dt": posted_dt,
        "link": _build_job_link(domain, path_prefix, job_url, job_id),
    }


def _search_page(
    session: requests.Session,
    domain: str,
    company_id_b64: str,
    start: int,
) -> List[dict]:
    filter_cri = {
        "paginationStartNo": start,
        "selectedCall": "sort",
        "sortCriteria": {"name": "modifiedDate", "isAscending": False},
        "anyOfTheseWords": "",
    }
    try:
        r = session.post(
            f"{API_BASE}/jobs/search",
            data={
                "filterCri": __import__("json").dumps(filter_cri, separators=(",", ":")),
                "domain": domain,
                "companyId": company_id_b64,
            },
            timeout=HTTP_TIMEOUT,
        )
        if not r.ok:
            return []
        payload = r.json()
    except Exception:
        return []

    if payload.get("code") != 200:
        return []

    data = payload.get("data") or {}
    jobs = data.get("data") if isinstance(data, dict) else []
    return jobs if isinstance(jobs, list) else []


def _fetch_jobs(
    session: requests.Session,
    domain: str,
    company_id: int | str,
    path_prefix: str = "",
    max_pages: int = DEFAULT_MAX_PAGES,
) -> List[dict]:
    max_pages = max(1, int(max_pages or DEFAULT_MAX_PAGES))
    company_id_b64 = _company_id_b64(company_id)
    if not domain or not company_id_b64:
        return []

    all_jobs: List[dict] = []
    seen = set()

    for page in range(max_pages):
        page_items = _search_page(session, domain, company_id_b64, page * PAGE_SIZE)
        if not page_items:
            break

        for item in page_items:
            parsed = _parse_search_item(item, domain, path_prefix)
            key = parsed.get("job_id") or parsed.get("link")
            if not key or key in seen:
                continue
            seen.add(key)
            all_jobs.append(parsed)

        if len(page_items) < PAGE_SIZE:
            break

        time.sleep(random.uniform(0.3, 0.6))

    return all_jobs


def scrape(
    keywords: List[str],
    company_name: str,
    locations: Optional[List[str]] = None,
    max_age_days: int = 1,
    domain: str = "",
    company_id: int | str = "",
    tenant_group_id: str = "",
    path_prefix: str = "",
    max_pages: int = DEFAULT_MAX_PAGES,
) -> List[Job]:
    """Scrape Zwayam/Openings.co and return matching jobs."""
    if not domain or not company_id:
        return []

    loc = [l.strip() for l in (locations or []) if l.strip()]
    cutoff = _now() - timedelta(days=max_age_days) if max_age_days > 0 else None
    results: List[Job] = []

    try:
        session = _make_session(tenant_group_id)
        raw_jobs = _fetch_jobs(
            session=session,
            domain=domain,
            company_id=company_id,
            path_prefix=path_prefix,
            max_pages=max_pages,
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

            posted_dt = item.get("posted_dt")
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
                posted_text=item.get("posted_text", ""),
                posted_dt=posted_dt,
            ))

        time.sleep(random.uniform(0.5, 1.0))
        return results

    except Exception:
        return []
