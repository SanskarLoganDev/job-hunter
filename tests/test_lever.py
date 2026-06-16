r"""
tests/test_lever.py

Tests for scrapers/lever.py.

All HTTP calls are mocked — tests run instantly and offline.
Fake responses mirror the real Lever v0 public API shape exactly.

Run with:  python -m pytest tests/test_lever.py -v
Live tests: set RUN_LIVE_TESTS=1 && .venv\Scripts\python -m pytest tests/test_lever.py::TestLive -v -s
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scrapers import Job
from scrapers.lever import (
    _parse_lever_date,
    _keyword_match,
    _location_match,
    _fetch_jobs,
    scrape,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_ms(dt: datetime) -> int:
    """Convert datetime to Unix milliseconds (Lever's date format)."""
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Helpers — mirror the real Lever v0 API response shape
# ---------------------------------------------------------------------------

def _make_api_response(jobs: list, ok: bool = True) -> MagicMock:
    r = MagicMock()
    r.ok = ok
    r.json.return_value = jobs   # Lever returns a plain array, not wrapped
    return r


def _make_job_item(
    title: str = "Software Engineer",
    location: str = "San Francisco, CA",
    days_old: int = 0,
    workplace_type: str = "",
    slug: str = "testco",
    job_id: str = "abc-123-def",
) -> dict:
    """Build a fake Lever job dict matching the real v0 API shape."""
    dt = _utcnow() - timedelta(days=days_old)
    return {
        "id":            job_id,
        "text":          title,           # Lever uses "text" for title
        "categories": {
            "location":   location,
            "team":       "Engineering",
            "department": "Platform",
        },
        "hostedUrl":     f"https://jobs.lever.co/{slug}/{job_id}",
        "applyUrl":      f"https://jobs.lever.co/{slug}/{job_id}/apply",
        "createdAt":     _to_ms(dt),      # milliseconds
        "workplaceType": workplace_type,
    }


# ---------------------------------------------------------------------------
# _parse_lever_date
# ---------------------------------------------------------------------------

class TestParseLeverDate(unittest.TestCase):

    def test_ms_timestamp(self):
        # 2026-06-15 00:00:00 UTC in milliseconds = 1781481600000
        # Verified: datetime(2026, 6, 15, tzinfo=timezone.utc).timestamp() * 1000
        ms = 1781481600000
        dt = _parse_lever_date(ms)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_result_is_timezone_aware(self):
        dt = _parse_lever_date(1781481600000)
        self.assertIsNotNone(dt.tzinfo)

    def test_none_returns_none(self):
        self.assertIsNone(_parse_lever_date(None))

    def test_zero_timestamp(self):
        # 0 ms = 1970-01-01 — should parse, not crash
        dt = _parse_lever_date(0)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 1970)

    def test_string_ms_also_works(self):
        # Some API responses return timestamps as strings
        dt = _parse_lever_date("1781481600000")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_lever_date("not-a-number"))


# ---------------------------------------------------------------------------
# _keyword_match / _location_match
# ---------------------------------------------------------------------------

class TestFilters(unittest.TestCase):

    def test_keyword_match(self):
        self.assertTrue(_keyword_match("Software Engineer", ["software"]))
        self.assertFalse(_keyword_match("Accountant", ["software"]))
        self.assertTrue(_keyword_match("Anything", []))

    def test_location_match(self):
        self.assertTrue(_location_match("San Francisco, CA", ["San Francisco"]))
        self.assertFalse(_location_match("Tel Aviv, Israel",
                                         ["San Francisco", "Remote"]))
        self.assertTrue(_location_match("Tel Aviv, Israel", []))

    def test_remote_appended_by_scraper(self):
        combined = "San Francisco, CA; Remote"
        self.assertTrue(_location_match(combined, ["Remote"]))


# ---------------------------------------------------------------------------
# _fetch_jobs
# ---------------------------------------------------------------------------

class TestFetchJobs(unittest.TestCase):

    def _mock_session(self, response: MagicMock) -> MagicMock:
        s = MagicMock()
        s.get.return_value = response
        return s

    def test_returns_jobs_on_success(self):
        jobs = [_make_job_item("Software Engineer")]
        result = _fetch_jobs("testco", self._mock_session(
            _make_api_response(jobs)))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "Software Engineer")

    def test_returns_empty_on_http_error(self):
        result = _fetch_jobs("testco", self._mock_session(
            _make_api_response([], ok=False)))
        self.assertEqual(result, [])

    def test_returns_empty_on_exception(self):
        s = MagicMock()
        s.get.side_effect = Exception("timeout")
        self.assertEqual(_fetch_jobs("testco", s), [])

    def test_returns_empty_on_non_list_response(self):
        r = MagicMock()
        r.ok = True
        r.json.return_value = {"error": "not found"}
        self.assertEqual(_fetch_jobs("testco", self._mock_session(r)), [])


# ---------------------------------------------------------------------------
# scrape()
# ---------------------------------------------------------------------------

class TestScrape(unittest.TestCase):

    def _patch_fetch(self, jobs: list):
        return patch("scrapers.lever._fetch_jobs", return_value=jobs)

    def test_returns_job_objects(self):
        fake = [_make_job_item("Software Engineer", "San Francisco, CA")]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["software"],
                          company_name="TestCo", locations=["San Francisco"],
                          max_age_days=1)
        self.assertEqual(len(jobs), 1)
        self.assertIsInstance(jobs[0], Job)

    def test_job_fields_populated(self):
        fake = [_make_job_item("Software Engineer", "New York, NY",
                               days_old=0, slug="testco", job_id="xyz-999")]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["software"],
                          company_name="TestCo", locations=[], max_age_days=0)
        j = jobs[0]
        self.assertEqual(j.title, "Software Engineer")
        self.assertEqual(j.company, "TestCo")
        self.assertIn("testco", j.link)
        self.assertIn("New York", j.location)
        self.assertIsNotNone(j.posted_dt)
        self.assertIsNotNone(j.posted_dt.tzinfo)
        self.assertRegex(j.posted_text, r"\d{4}-\d{2}-\d{2}")

    def test_title_from_text_field(self):
        fake = [_make_job_item("Backend Engineer", "Remote")]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["backend"],
                          company_name="TestCo", locations=[], max_age_days=0)
        self.assertEqual(jobs[0].title, "Backend Engineer")

    def test_keyword_filter(self):
        fake = [
            _make_job_item("Software Engineer", "Remote"),
            _make_job_item("Accountant", "Remote", job_id="acct-001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["software", "engineer"],
                          company_name="TestCo", locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Software Engineer")

    def test_seniority_filter(self):
        fake = [
            _make_job_item("Software Engineer", "Remote"),
            _make_job_item("Senior Software Engineer", "Remote", job_id="sr-001"),
            _make_job_item("Staff Engineer", "Remote", job_id="staff-001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        titles = [j.title for j in jobs]
        self.assertIn("Software Engineer", titles)
        self.assertNotIn("Senior Software Engineer", titles)
        self.assertNotIn("Staff Engineer", titles)

    def test_location_filter(self):
        fake = [
            _make_job_item("Software Engineer", "San Francisco, CA"),
            _make_job_item("Software Engineer", "Tel Aviv, Israel", job_id="il-001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo",
                          locations=["San Francisco", "Remote"],
                          max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertNotIn("Israel", jobs[0].location)

    def test_remote_workplace_type_matched(self):
        fake = [_make_job_item("Software Engineer", "Anywhere",
                               workplace_type="Remote")]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo",
                          locations=["Remote"],
                          max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertIn("Remote", jobs[0].location)

    def test_age_filter_drops_old(self):
        fake = [
            _make_job_item("Software Engineer", "Remote", days_old=0),
            _make_job_item("Software Engineer", "Remote", days_old=5,
                           job_id="old-001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=1)
        self.assertEqual(len(jobs), 1)

    def test_age_filter_zero_keeps_all(self):
        fake = [
            _make_job_item("Software Engineer", "Remote", days_old=0),
            _make_job_item("Software Engineer", "Remote", days_old=30,
                           job_id="old-001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 2)

    def test_createdat_ms_timestamp_parsed(self):
        fake = [_make_job_item("Software Engineer", "Remote", days_old=0)]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        self.assertIsNotNone(jobs[0].posted_dt)
        diff = abs((_utcnow() - jobs[0].posted_dt).total_seconds())
        self.assertLess(diff, 10, "posted_dt should be approximately now")

    def test_never_raises(self):
        with patch("scrapers.lever._fetch_jobs", side_effect=Exception("boom")):
            jobs = scrape(slug="testco", keywords=["software"],
                          company_name="TestCo")
        self.assertEqual(jobs, [])

    def test_uid_stable_across_runs(self):
        fake = [_make_job_item("Software Engineer", "Remote", job_id="uid-test")]
        with self._patch_fetch(fake):
            jobs1 = scrape(slug="testco", keywords=[], company_name="TestCo",
                           locations=[], max_age_days=0)
        with self._patch_fetch(fake):
            jobs2 = scrape(slug="testco", keywords=[], company_name="TestCo",
                           locations=[], max_age_days=0)
        self.assertEqual({j.uid for j in jobs1}, {j.uid for j in jobs2})

    def test_empty_api_returns_empty(self):
        with self._patch_fetch([]):
            jobs = scrape(slug="testco", keywords=["software"],
                          company_name="TestCo", max_age_days=1)
        self.assertEqual(jobs, [])


# ---------------------------------------------------------------------------
# Live tests — hit the real Lever API
# Run: set RUN_LIVE_TESTS=1 && .venv\Scripts\python -m pytest tests/test_lever.py::TestLive -v -s
# ---------------------------------------------------------------------------

class TestLive(unittest.TestCase):

    def setUp(self):
        import os
        if not os.getenv("RUN_LIVE_TESTS"):
            self.skipTest(
                "Live tests skipped. "
                r"Run: set RUN_LIVE_TESTS=1 && "
                r".venv\Scripts\python -m pytest tests/test_lever.py::TestLive -v -s"
            )

    def test_voleon_returns_jobs(self):
        jobs = scrape(
            slug="voleon",
            keywords=["software", "engineer", "backend", "python"],
            company_name="Voleon Group",
            locations=[],
            max_age_days=0,
        )
        print(f"\nVoleon: {len(jobs)} total jobs")
        for j in jobs[:5]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        self.assertIsInstance(jobs, list)

    def test_nimblerx_returns_jobs(self):
        jobs = scrape(
            slug="nimblerx",
            keywords=["software", "engineer", "backend"],
            company_name="NimbleRx",
            locations=[],
            max_age_days=0,
        )
        print(f"\nNimbleRx: {len(jobs)} total jobs")
        for j in jobs[:5]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        self.assertIsInstance(jobs, list)

    def test_print_location_strings(self):
        jobs = scrape(
            slug="voleon",
            keywords=[],
            company_name="Voleon Group",
            locations=[],
            max_age_days=0,
        )
        locations = sorted({j.location for j in jobs})
        print(f"\nVoleon raw location strings ({len(locations)} unique):")
        for loc in locations:
            print(f"  '{loc}'")
        self.assertIsInstance(jobs, list)

    def test_createdat_is_real_date(self):
        jobs = scrape(
            slug="voleon",
            keywords=[],
            company_name="Voleon Group",
            locations=[],
            max_age_days=0,
        )
        if not jobs:
            self.skipTest("No jobs returned")
        jobs_with_date = [j for j in jobs if j.posted_dt is not None]
        pct = len(jobs_with_date) / len(jobs) * 100
        print(f"\nVoleon: {len(jobs_with_date)}/{len(jobs)} jobs have createdAt ({pct:.0f}%)")
        self.assertGreater(pct, 90, "Fewer than 90% of jobs have createdAt")


if __name__ == "__main__":
    unittest.main()
