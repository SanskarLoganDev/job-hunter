"""
tests/test_scrapers.py

Tests for scrapers/amazon.py and scrapers/__init__.py (is_junior_enough).

No real HTTP calls — all network activity is mocked.

Run with:  python -m pytest tests/test_scrapers.py -v
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scrapers import Job, is_junior_enough
from scrapers.amazon import (
    _parse_date,
    _normalize_link,
    _extract_jobs_from_html,
    _filter_age,
    scrape,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# is_junior_enough
# ---------------------------------------------------------------------------

class TestIsJuniorEnough(unittest.TestCase):

    def test_plain_swe_passes(self):
        self.assertTrue(is_junior_enough("Software Engineer"))

    def test_new_grad_passes(self):
        self.assertTrue(is_junior_enough("Software Engineer, New Grad"))

    def test_entry_level_passes(self):
        self.assertTrue(is_junior_enough("Entry Level Python Developer"))

    def test_senior_excluded(self):
        self.assertFalse(is_junior_enough("Senior Software Engineer"))

    def test_sr_dot_excluded(self):
        self.assertFalse(is_junior_enough("Sr. Software Engineer"))

    def test_staff_excluded(self):
        self.assertFalse(is_junior_enough("Staff Engineer"))

    def test_principal_excluded(self):
        self.assertFalse(is_junior_enough("Principal Software Engineer"))

    def test_lead_excluded(self):
        self.assertFalse(is_junior_enough("Lead Backend Engineer"))

    def test_director_excluded(self):
        self.assertFalse(is_junior_enough("Director of Engineering"))

    def test_manager_excluded(self):
        self.assertFalse(is_junior_enough("Engineering Manager"))

    def test_vp_excluded(self):
        self.assertFalse(is_junior_enough("VP Engineering"))

    def test_head_of_excluded(self):
        self.assertFalse(is_junior_enough("Head of Platform Engineering"))

    def test_case_insensitive(self):
        self.assertFalse(is_junior_enough("SENIOR SOFTWARE ENGINEER"))

    def test_mid_level_passes(self):
        self.assertTrue(is_junior_enough("Mid-Level Software Engineer"))

    def test_safeguards_does_not_trigger_lead(self):
        self.assertTrue(is_junior_enough("Software Engineer, Safeguards"))


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

class TestParseDate(unittest.TestCase):

    def test_iso_date(self):
        txt, dt = _parse_date("Posted 2026-06-15")
        self.assertEqual(txt, "2026-06-15")
        self.assertEqual(dt, datetime(2026, 6, 15, tzinfo=timezone.utc))

    def test_month_name(self):
        txt, dt = _parse_date("June 15, 2026")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_relative_days(self):
        _, dt = _parse_date("3 days ago")
        expected = _utcnow() - timedelta(days=3)
        self.assertAlmostEqual(dt.timestamp(), expected.timestamp(), delta=5)

    def test_relative_hours(self):
        _, dt = _parse_date("2 hours ago")
        expected = _utcnow() - timedelta(hours=2)
        self.assertAlmostEqual(dt.timestamp(), expected.timestamp(), delta=5)

    def test_returned_datetime_is_timezone_aware(self):
        for text in ["2026-06-15", "June 15, 2026", "3 days ago", "2 hours ago"]:
            _, dt = _parse_date(text)
            self.assertIsNotNone(dt, f"Expected a datetime for '{text}'")
            self.assertIsNotNone(dt.tzinfo, f"Expected timezone-aware datetime for '{text}'")

    def test_empty_string(self):
        txt, dt = _parse_date("")
        self.assertIsNone(txt)
        self.assertIsNone(dt)

    def test_no_date(self):
        _, dt = _parse_date("Senior Software Engineer")
        self.assertIsNone(dt)


# ---------------------------------------------------------------------------
# _normalize_link
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# _extract_jobs_from_html
# ---------------------------------------------------------------------------

class TestExtractJobsFromHtml(unittest.TestCase):

    def _make_html(self, href: str, title: str) -> str:
        return f"""<html><body>
        <a href="{href}">{title}</a>
        </body></html>"""

    def test_picks_up_valid_job_link(self):
        html = self._make_html("/en/jobs/123/software-engineer", "Software Engineer")
        jobs = _extract_jobs_from_html(html, ["software"], [])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Software Engineer")

    def test_filters_by_keyword(self):
        html = self._make_html("/en/jobs/123/accountant", "Accountant")
        jobs = _extract_jobs_from_html(html, ["software", "engineer"], [])
        self.assertEqual(len(jobs), 0)

    def test_no_keyword_filter_returns_all_non_senior(self):
        html = self._make_html("/en/jobs/123/accountant", "Accountant")
        jobs = _extract_jobs_from_html(html, [], [])
        self.assertEqual(len(jobs), 1)

    def test_senior_title_excluded(self):
        html = self._make_html("/en/jobs/123/swe", "Senior Software Engineer")
        jobs = _extract_jobs_from_html(html, [], [])
        self.assertEqual(len(jobs), 0)

    def test_ignores_non_job_links(self):
        html = self._make_html("https://www.amazon.com/shop", "Buy Now")
        jobs = _extract_jobs_from_html(html, [], [])
        self.assertEqual(len(jobs), 0)

    def test_deduplicates(self):
        html = """<html><body>
        <a href="/en/jobs/1/swe">Software Engineer</a>
        <a href="/en/jobs/1/swe">Software Engineer</a>
        </body></html>"""
        jobs = _extract_jobs_from_html(html, [], [])
        self.assertEqual(len(jobs), 1)


# ---------------------------------------------------------------------------
# _filter_age
# ---------------------------------------------------------------------------

class TestFilterAge(unittest.TestCase):

    def _make_raw(self, days_old: int) -> dict:
        return {
            "title":       "SWE",
            "link":        "https://www.amazon.jobs/en/jobs/1/swe",
            "location":    "",
            "posted_text": "",
            "posted_dt":   _utcnow() - timedelta(days=days_old),
        }

    def test_recent_job_passes(self):
        self.assertEqual(len(_filter_age([self._make_raw(1)], 7)), 1)

    def test_old_job_filtered(self):
        self.assertEqual(len(_filter_age([self._make_raw(10)], 7)), 0)

    def test_no_date_filtered(self):
        raw = [{"title": "SWE", "link": "x", "location": "",
                "posted_text": "", "posted_dt": None}]
        self.assertEqual(len(_filter_age(raw, 7)), 0)

    def test_zero_max_age_keeps_all(self):
        raw = [self._make_raw(30), self._make_raw(1)]
        self.assertEqual(len(_filter_age(raw, 0)), 2)


# ---------------------------------------------------------------------------
# scrape() integration
# ---------------------------------------------------------------------------

class TestScrapeIntegration(unittest.TestCase):

    _FAKE_JSON = {
        "jobs": [
            {
                "title":       "Software Engineer",
                "job_path":    "/en/jobs/100/swe",
                "location":    "Seattle, WA",
                "posted_date": (_utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
            },
            {
                "title":       "Python Developer",
                "job_path":    "/en/jobs/101/python-dev",
                "location":    "Remote",
                "posted_date": (_utcnow() - timedelta(days=2)).strftime("%Y-%m-%d"),
            },
            {
                "title":       "Senior Software Engineer",
                "job_path":    "/en/jobs/103/senior-swe",
                "location":    "Seattle, WA",
                "posted_date": (_utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
            },
            {
                "title":       "Accountant",
                "job_path":    "/en/jobs/102/acct",
                "location":    "New York",
                "posted_date": (_utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
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
        MockSession.return_value.get.return_value = self._make_mock_response()
        jobs = scrape(keywords=["software", "python", "developer", "engineer"],
                      max_age_days=7, detail_fetch_limit=0)
        self.assertTrue(all(isinstance(j, Job) for j in jobs))

    @patch("scrapers.amazon.requests.Session")
    def test_keyword_filter_removes_accountant(self, MockSession):
        MockSession.return_value.get.return_value = self._make_mock_response()
        jobs = scrape(keywords=["software", "python", "developer", "engineer"],
                      max_age_days=7, detail_fetch_limit=0)
        self.assertNotIn("Accountant", [j.title for j in jobs])

    @patch("scrapers.amazon.requests.Session")
    def test_seniority_filter_removes_senior_swe(self, MockSession):
        MockSession.return_value.get.return_value = self._make_mock_response()
        jobs = scrape(keywords=["software", "python", "developer", "engineer"],
                      max_age_days=7, detail_fetch_limit=0)
        self.assertNotIn("Senior Software Engineer", [j.title for j in jobs])

    @patch("scrapers.amazon.requests.Session")
    def test_returns_empty_on_http_failure(self, MockSession):
        MockSession.return_value.get.return_value = self._make_mock_response(ok=False)
        self.assertEqual(scrape(keywords=["software"], max_age_days=7,
                                detail_fetch_limit=0), [])

    @patch("scrapers.amazon.requests.Session")
    def test_never_raises(self, MockSession):
        MockSession.side_effect = Exception("total network failure")
        self.assertEqual(scrape(keywords=["software"], max_age_days=7,
                                detail_fetch_limit=0), [])

    @patch("scrapers.amazon.requests.Session")
    def test_uid_is_stable(self, MockSession):
        MockSession.return_value.get.return_value = self._make_mock_response()
        jobs1 = scrape(keywords=["software", "python", "engineer"],
                       max_age_days=7, detail_fetch_limit=0)
        jobs2 = scrape(keywords=["software", "python", "engineer"],
                       max_age_days=7, detail_fetch_limit=0)
        self.assertEqual({j.uid for j in jobs1}, {j.uid for j in jobs2})


if __name__ == "__main__":
    unittest.main()
