"""
tests/test_scrapers.py

Tests for scrapers/amazon.py.

No real HTTP calls are made — all network activity is mocked using
unittest.mock.patch so tests run instantly and offline.

Run with:  python -m pytest tests/test_scrapers.py -v
"""

import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from scrapers import Job
from scrapers.amazon import (
    _parse_date,
    _normalize_link,
    _extract_jobs_from_html,
    _filter_age,
    scrape,
)


class TestParseDate(unittest.TestCase):

    def test_iso_date(self):
        txt, dt = _parse_date("Posted 2025-06-01")
        self.assertEqual(txt, "2025-06-01")
        self.assertEqual(dt, datetime(2025, 6, 1))

    def test_month_name(self):
        txt, dt = _parse_date("June 5, 2025")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 5)

    def test_relative_days(self):
        _, dt = _parse_date("3 days ago")
        expected = datetime.utcnow() - timedelta(days=3)
        self.assertAlmostEqual(dt.timestamp(), expected.timestamp(), delta=5)

    def test_relative_hours(self):
        _, dt = _parse_date("2 hours ago")
        expected = datetime.utcnow() - timedelta(hours=2)
        self.assertAlmostEqual(dt.timestamp(), expected.timestamp(), delta=5)

    def test_empty_string(self):
        txt, dt = _parse_date("")
        self.assertIsNone(txt)
        self.assertIsNone(dt)

    def test_no_date(self):
        txt, dt = _parse_date("Senior Software Engineer")
        self.assertIsNone(dt)


class TestNormalizeLink(unittest.TestCase):

    def test_valid_absolute(self):
        url = "https://www.amazon.jobs/en/jobs/12345/swe"
        self.assertEqual(_normalize_link(url), url)

    def test_relative_en_jobs(self):
        result = _normalize_link("/en/jobs/12345/swe")
        self.assertTrue(result.startswith("https://www.amazon.jobs"))

    def test_relative_jobs(self):
        result = _normalize_link("/jobs/12345/swe")
        self.assertTrue(result.startswith("https://www.amazon.jobs"))

    def test_non_job_url(self):
        self.assertEqual(_normalize_link("https://account.amazon.com/login"), "")

    def test_empty(self):
        self.assertEqual(_normalize_link(""), "")

    def test_whitespace_stripped(self):
        result = _normalize_link("  /en/jobs/99/engineer  ")
        self.assertTrue(result.startswith("https://"))


class TestExtractJobsFromHtml(unittest.TestCase):

    def _make_html(self, href: str, title: str) -> str:
        return f"""<html><body>
        <a href="{href}">{title}</a>
        </body></html>"""

    def test_picks_up_valid_job_link(self):
        html = self._make_html(
            "/en/jobs/123/software-engineer",
            "Software Engineer"
        )
        jobs = _extract_jobs_from_html(html, ["software"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Software Engineer")

    def test_filters_by_keyword(self):
        html = self._make_html("/en/jobs/123/accountant", "Accountant")
        jobs = _extract_jobs_from_html(html, ["software", "engineer"])
        self.assertEqual(len(jobs), 0)

    def test_no_keyword_filter_returns_all(self):
        html = self._make_html("/en/jobs/123/accountant", "Accountant")
        jobs = _extract_jobs_from_html(html, [])
        self.assertEqual(len(jobs), 1)

    def test_ignores_non_job_links(self):
        html = self._make_html("https://www.amazon.com/shop", "Buy Now")
        jobs = _extract_jobs_from_html(html, [])
        self.assertEqual(len(jobs), 0)

    def test_deduplicates(self):
        html = """<html><body>
        <a href="/en/jobs/1/swe">Software Engineer</a>
        <a href="/en/jobs/1/swe">Software Engineer</a>
        </body></html>"""
        jobs = _extract_jobs_from_html(html, [])
        self.assertEqual(len(jobs), 1)


class TestFilterAge(unittest.TestCase):

    def _make_raw(self, days_old: int) -> dict:
        return {
            "title": "SWE",
            "link": "https://www.amazon.jobs/en/jobs/1/swe",
            "location": "",
            "posted_text": "",
            "posted_dt": datetime.utcnow() - timedelta(days=days_old),
        }

    def test_recent_job_passes(self):
        raw = [self._make_raw(1)]
        result = _filter_age(raw, max_age_days=7)
        self.assertEqual(len(result), 1)

    def test_old_job_filtered(self):
        raw = [self._make_raw(10)]
        result = _filter_age(raw, max_age_days=7)
        self.assertEqual(len(result), 0)

    def test_no_date_filtered(self):
        raw = [{"title": "SWE", "link": "x", "location": "",
                "posted_text": "", "posted_dt": None}]
        result = _filter_age(raw, max_age_days=7)
        self.assertEqual(len(result), 0)

    def test_zero_max_age_keeps_all(self):
        raw = [self._make_raw(30), self._make_raw(1)]
        result = _filter_age(raw, max_age_days=0)
        self.assertEqual(len(result), 2)


class TestScrapeIntegration(unittest.TestCase):
    """
    Tests the full scrape() function with mocked HTTP.
    The mock returns a realistic Amazon search.json response.
    """

    _FAKE_JSON = {
        "jobs": [
            {
                "title": "Software Engineer",
                "job_path": "/en/jobs/100/swe",
                "location": "Seattle, WA",
                "posted_date": (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
            },
            {
                "title": "Python Developer",
                "job_path": "/en/jobs/101/python-dev",
                "location": "Remote",
                "posted_date": (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d"),
            },
            {
                "title": "Accountant",           # should be filtered by keyword
                "job_path": "/en/jobs/102/acct",
                "location": "New York",
                "posted_date": (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
            },
        ]
    }

    def _make_mock_response(self, ok=True, json_data=None):
        r = MagicMock()
        r.ok = ok
        r.json.return_value = json_data or self._FAKE_JSON
        r.text = ""
        return r

    @patch("scrapers.amazon.requests.Session")
    def test_returns_job_objects(self, MockSession):
        session_instance = MockSession.return_value
        session_instance.get.return_value = self._make_mock_response()

        jobs = scrape(
            keywords=["software", "python", "developer", "engineer"],
            max_age_days=7,
            detail_fetch_limit=0,   # skip detail fetching in tests
        )

        self.assertIsInstance(jobs, list)
        self.assertTrue(all(isinstance(j, Job) for j in jobs))

    @patch("scrapers.amazon.requests.Session")
    def test_keyword_filter_applied(self, MockSession):
        session_instance = MockSession.return_value
        session_instance.get.return_value = self._make_mock_response()

        jobs = scrape(
            keywords=["software", "python", "developer", "engineer"],
            max_age_days=7,
            detail_fetch_limit=0,
        )

        titles = [j.title for j in jobs]
        self.assertNotIn("Accountant", titles)

    @patch("scrapers.amazon.requests.Session")
    def test_returns_empty_on_http_failure(self, MockSession):
        session_instance = MockSession.return_value
        session_instance.get.return_value = self._make_mock_response(ok=False)

        jobs = scrape(keywords=["software"], max_age_days=7, detail_fetch_limit=0)
        self.assertEqual(jobs, [])

    @patch("scrapers.amazon.requests.Session")
    def test_never_raises(self, MockSession):
        MockSession.side_effect = Exception("total network failure")
        # Should not raise — scraper swallows all errors
        jobs = scrape(keywords=["software"], max_age_days=7, detail_fetch_limit=0)
        self.assertEqual(jobs, [])

    @patch("scrapers.amazon.requests.Session")
    def test_uid_is_stable(self, MockSession):
        session_instance = MockSession.return_value
        session_instance.get.return_value = self._make_mock_response()

        jobs1 = scrape(keywords=["software", "python", "engineer"],
                       max_age_days=7, detail_fetch_limit=0)
        jobs2 = scrape(keywords=["software", "python", "engineer"],
                       max_age_days=7, detail_fetch_limit=0)

        uids1 = {j.uid for j in jobs1}
        uids2 = {j.uid for j in jobs2}
        self.assertEqual(uids1, uids2)


if __name__ == "__main__":
    unittest.main()
