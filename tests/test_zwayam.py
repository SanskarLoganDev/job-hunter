"""
tests/test_zwayam.py

Tests for scrapers/zwayam.py.

All HTTP calls are mocked — tests run offline.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scrapers import Job
from scrapers.zwayam import (
    _build_job_link,
    _company_id_b64,
    _fetch_jobs,
    _keyword_match,
    _location_match,
    _parse_epoch_ms,
    _parse_search_item,
    scrape,
)


def _epoch_ms(days_old: int = 0) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days_old)).timestamp() * 1000)


def _item(
    title: str = "Cloud Engineer",
    job_id: int = 1167357,
    job_url: str = "cloud-engineer-chicago-il-usa-2026091000000000",
    location: str = "Chicago, IL, USA",
    created_ms: int | None = None,
) -> dict:
    return {
        "_source": {
            "id": job_id,
            "jobTitle": title,
            "jobUrl": job_url,
            "location": location,
            "createdDate": _epoch_ms() if created_ms is None else created_ms,
            "jobCode": "14101",
        }
    }


class TestHelpers(unittest.TestCase):

    def test_company_id_b64_encodes_numeric_id(self):
        self.assertEqual(_company_id_b64(15166), "MTUxNjY=")
        self.assertEqual(_company_id_b64("MTUxNjY="), "MTUxNjY=")

    def test_parse_epoch_ms(self):
        dt = _parse_epoch_ms(1787318065000)

        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.year, 2026)

    def test_build_job_link(self):
        self.assertEqual(
            _build_job_link(
                "impetus.openings.co",
                "impetus",
                "cloud-engineer-chicago-il-usa-2026091000000000",
                "1167357",
            ),
            "https://impetus.openings.co/impetus/jobview/cloud-engineer-chicago-il-usa-2026091000000000?id=1167357",
        )

    def test_parse_search_item(self):
        parsed = _parse_search_item(_item(), "impetus.openings.co", "impetus")

        self.assertEqual(parsed["title"], "Cloud Engineer")
        self.assertEqual(parsed["job_id"], "1167357")
        self.assertEqual(parsed["location"], "Chicago, IL, USA")
        self.assertIn("/impetus/jobview/", parsed["link"])
        self.assertIsNotNone(parsed["posted_dt"])

    def test_filters_use_shared_rules(self):
        self.assertTrue(_keyword_match("Cloud Engineer", ["cloud engineer"]))
        self.assertFalse(_keyword_match("Accountant", ["cloud engineer"]))
        self.assertTrue(_location_match("Chicago, IL, USA", ["United States"]))
        self.assertFalse(_location_match("Chennai, India", ["United States"]))


class TestFetchJobs(unittest.TestCase):

    def test_fetches_and_deduplicates_pages(self):
        session = MagicMock()
        first_page = [_item(job_id=i) for i in range(1, 11)]
        session.post.side_effect = [
            MagicMock(ok=True, json=lambda: {"code": 200, "data": {"data": first_page}}),
            MagicMock(ok=True, json=lambda: {"code": 200, "data": {"data": [_item(job_id=1)]}}),
        ]

        jobs = _fetch_jobs(
            session=session,
            domain="impetus.openings.co",
            company_id=15166,
            path_prefix="impetus",
            max_pages=2,
        )

        self.assertEqual(len(jobs), 10)
        self.assertEqual(session.post.call_count, 2)

    def test_returns_empty_on_http_error(self):
        session = MagicMock()
        session.post.return_value = MagicMock(ok=False)

        self.assertEqual(_fetch_jobs(session, "impetus.openings.co", 15166), [])


class TestScrape(unittest.TestCase):

    def _patch_fetch(self, jobs: list):
        return patch("scrapers.zwayam._fetch_jobs", return_value=jobs)

    def test_returns_job_objects(self):
        raw = [_parse_search_item(_item(), "impetus.openings.co", "impetus")]

        with self._patch_fetch(raw):
            jobs = scrape(
                keywords=["cloud engineer"],
                company_name="Impetus",
                locations=["United States"],
                max_age_days=1,
                domain="impetus.openings.co",
                company_id=15166,
                tenant_group_id="G1",
                path_prefix="impetus",
            )

        self.assertEqual(len(jobs), 1)
        self.assertIsInstance(jobs[0], Job)
        self.assertEqual(jobs[0].title, "Cloud Engineer")
        self.assertEqual(jobs[0].company, "Impetus")

    def test_filters_keyword_seniority_location_and_age(self):
        raw = [
            _parse_search_item(_item(title="Cloud Engineer", job_id=1), "impetus.openings.co", "impetus"),
            _parse_search_item(_item(title="Senior Cloud Engineer", job_id=2), "impetus.openings.co", "impetus"),
            _parse_search_item(_item(title="Accountant", job_id=3), "impetus.openings.co", "impetus"),
            _parse_search_item(_item(title="Cloud Engineer", job_id=4, location="Chennai, India"), "impetus.openings.co", "impetus"),
            _parse_search_item(_item(title="Cloud Engineer", job_id=5, created_ms=_epoch_ms(days_old=5)), "impetus.openings.co", "impetus"),
        ]

        with self._patch_fetch(raw):
            jobs = scrape(
                keywords=["cloud engineer"],
                company_name="Impetus",
                locations=["United States"],
                max_age_days=1,
                domain="impetus.openings.co",
                company_id=15166,
            )

        self.assertEqual([job.title for job in jobs], ["Cloud Engineer"])


if __name__ == "__main__":
    unittest.main()
