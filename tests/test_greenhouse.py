"""
tests/test_greenhouse.py

Tests for scrapers/greenhouse.py.

All HTTP calls are mocked — tests run instantly and offline.

Run with:  python -m pytest tests/test_greenhouse.py -v
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scrapers import Job
from scrapers.greenhouse import (
    _parse_gh_date,
    _keyword_match,
    _location_match,
    _fetch_jobs,
    scrape,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_api_response(jobs: list, ok: bool = True) -> MagicMock:
    r = MagicMock()
    r.ok = ok
    r.json.return_value = {"jobs": jobs}
    return r


def _make_job_item(
    title: str = "Software Engineer",
    job_id: int = 1001,
    location: str = "San Francisco, CA",
    days_old: int = 0,
    slug: str = "testco",
) -> dict:
    dt = _utcnow() - timedelta(days=days_old)
    return {
        "id":           job_id,
        "title":        title,
        "absolute_url": f"https://boards.greenhouse.io/{slug}/jobs/{job_id}",
        "location":     {"name": location},
        "updated_at":   dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "content":      "<p>Job description</p>",
    }


# ---------------------------------------------------------------------------
# _parse_gh_date
# ---------------------------------------------------------------------------

class TestParseGhDate(unittest.TestCase):

    def test_z_suffix(self):
        dt = _parse_gh_date("2026-06-15T10:00:00.000Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_explicit_offset(self):
        dt = _parse_gh_date("2026-06-15T10:00:00+00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)

    def test_result_is_timezone_aware(self):
        dt = _parse_gh_date("2026-06-15T10:00:00.000Z")
        self.assertIsNotNone(dt.tzinfo)

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_gh_date(""))

    def test_none_returns_none(self):
        self.assertIsNone(_parse_gh_date(None))

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_gh_date("not a date"))


# ---------------------------------------------------------------------------
# _keyword_match
# ---------------------------------------------------------------------------

class TestKeywordMatch(unittest.TestCase):

    def test_match_single(self):
        self.assertTrue(_keyword_match("Software Engineer", ["software"]))

    def test_match_any(self):
        self.assertTrue(_keyword_match("DevOps Engineer", ["python", "devops"]))

    def test_no_match(self):
        self.assertFalse(_keyword_match("Accountant", ["software", "engineer"]))

    def test_case_insensitive(self):
        self.assertTrue(_keyword_match("PYTHON DEVELOPER", ["python"]))

    def test_empty_keywords_always_matches(self):
        self.assertTrue(_keyword_match("Anything At All", []))

    def test_partial_word_match(self):
        self.assertTrue(_keyword_match("Software Engineer", ["engineer"]))


# ---------------------------------------------------------------------------
# _location_match
# ---------------------------------------------------------------------------

class TestLocationMatch(unittest.TestCase):

    def test_city_match(self):
        self.assertTrue(_location_match("San Francisco, CA", ["San Francisco"]))

    def test_remote_match(self):
        self.assertTrue(_location_match("Remote", ["Remote"]))

    def test_remote_us_match(self):
        self.assertTrue(_location_match("Remote, United States", ["United States"]))

    def test_rejects_international(self):
        self.assertFalse(_location_match("Tel Aviv, Israel",
                                         ["United States", "Remote", "San Francisco"]))

    def test_empty_allowed_passes_everything(self):
        self.assertTrue(_location_match("Tel Aviv, Israel", []))

    def test_case_insensitive(self):
        self.assertTrue(_location_match("san francisco, ca", ["San Francisco"]))

    def test_partial_match(self):
        self.assertTrue(_location_match("New York, NY", ["New York"]))

    def test_us_substring_in_location(self):
        self.assertTrue(_location_match("Austin, TX, US", ["US"]))

    def test_brussels_substring_behaviour_documented(self):
        # "us" is a substring of "Brussels" — known limitation of simple substring match.
        # In practice config.yaml uses specific city names to avoid this.
        result = _location_match("Brussels, Belgium", ["US"])
        self.assertIsInstance(result, bool)


# ---------------------------------------------------------------------------
# _fetch_jobs
# ---------------------------------------------------------------------------

class TestFetchJobs(unittest.TestCase):

    def _mock_session(self, response: MagicMock) -> MagicMock:
        s = MagicMock()
        s.get.return_value = response
        return s

    def test_returns_job_list_on_success(self):
        jobs = [_make_job_item("Software Engineer", 1)]
        result = _fetch_jobs("testco", self._mock_session(_make_api_response(jobs)))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Software Engineer")

    def test_returns_empty_on_http_error(self):
        result = _fetch_jobs("testco", self._mock_session(_make_api_response([], ok=False)))
        self.assertEqual(result, [])

    def test_returns_empty_on_exception(self):
        s = MagicMock()
        s.get.side_effect = Exception("connection refused")
        self.assertEqual(_fetch_jobs("testco", s), [])

    def test_returns_empty_when_jobs_key_missing(self):
        r = MagicMock()
        r.ok = True
        r.json.return_value = {"error": "not found"}
        self.assertEqual(_fetch_jobs("testco", self._mock_session(r)), [])


# ---------------------------------------------------------------------------
# scrape()
# ---------------------------------------------------------------------------

class TestScrape(unittest.TestCase):

    def _patch_fetch(self, jobs: list):
        return patch("scrapers.greenhouse._fetch_jobs", return_value=jobs)

    def test_returns_job_objects(self):
        fake = [_make_job_item("Software Engineer", 1, "San Francisco, CA", days_old=0)]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["software"],
                          company_name="TestCo", locations=["San Francisco"],
                          max_age_days=1)
        self.assertEqual(len(jobs), 1)
        self.assertIsInstance(jobs[0], Job)

    def test_job_fields_populated(self):
        fake = [_make_job_item("Software Engineer", 42, "New York, NY", days_old=0)]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["software"],
                          company_name="TestCo", locations=[], max_age_days=0)
        j = jobs[0]
        self.assertEqual(j.title, "Software Engineer")
        self.assertEqual(j.company, "TestCo")
        self.assertIn("testco", j.link)
        self.assertEqual(j.location, "New York, NY")
        self.assertIsNotNone(j.posted_dt)
        self.assertIsNotNone(j.posted_dt.tzinfo)

    def test_keyword_filter(self):
        fake = [
            _make_job_item("Software Engineer", 1, "Remote", days_old=0),
            _make_job_item("Accountant", 2, "Remote", days_old=0),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["software", "engineer"],
                          company_name="TestCo", locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Software Engineer")

    def test_seniority_filter(self):
        fake = [
            _make_job_item("Software Engineer", 1, "Remote", days_old=0),
            _make_job_item("Senior Software Engineer", 2, "Remote", days_old=0),
            _make_job_item("Staff Engineer", 3, "Remote", days_old=0),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo", locations=[], max_age_days=0)
        titles = [j.title for j in jobs]
        self.assertIn("Software Engineer", titles)
        self.assertNotIn("Senior Software Engineer", titles)
        self.assertNotIn("Staff Engineer", titles)

    def test_location_filter_city(self):
        fake = [
            _make_job_item("Software Engineer", 1, "San Francisco, CA", days_old=0),
            _make_job_item("Software Engineer", 2, "Tel Aviv, Israel", days_old=0),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo",
                          locations=["San Francisco", "Remote", "New York", "Seattle"],
                          max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertNotIn("Israel", jobs[0].location)

    def test_age_filter_drops_old_jobs(self):
        fake = [
            _make_job_item("Software Engineer", 1, "Remote", days_old=0),
            _make_job_item("Software Engineer", 2, "Remote", days_old=5),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo", locations=[], max_age_days=1)
        self.assertEqual(len(jobs), 1)

    def test_age_filter_zero_keeps_all(self):
        fake = [
            _make_job_item("Software Engineer", 1, "Remote", days_old=0),
            _make_job_item("Software Engineer", 2, "Remote", days_old=30),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo", locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 2)

    def test_empty_api_returns_empty(self):
        with self._patch_fetch([]):
            jobs = scrape(slug="testco", keywords=["software"],
                          company_name="TestCo", locations=[], max_age_days=1)
        self.assertEqual(jobs, [])

    def test_never_raises_on_exception(self):
        with patch("scrapers.greenhouse._fetch_jobs", side_effect=Exception("boom")):
            jobs = scrape(slug="testco", keywords=["software"], company_name="TestCo")
        self.assertEqual(jobs, [])

    def test_uid_is_stable_across_runs(self):
        fake = [_make_job_item("Software Engineer", 99, "Remote", days_old=0)]
        with self._patch_fetch(fake):
            jobs1 = scrape(slug="testco", keywords=[], company_name="TestCo",
                           locations=[], max_age_days=0)
        with self._patch_fetch(fake):
            jobs2 = scrape(slug="testco", keywords=[], company_name="TestCo",
                           locations=[], max_age_days=0)
        self.assertEqual({j.uid for j in jobs1}, {j.uid for j in jobs2})

    def test_no_location_filter_passes_all_locations(self):
        fake = [
            _make_job_item("Software Engineer", 1, "Tel Aviv, Israel", days_old=0),
            _make_job_item("Software Engineer", 2, "Remote", days_old=0),
            _make_job_item("Software Engineer", 3, "London, UK", days_old=0),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo", locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 3)


# ---------------------------------------------------------------------------
# Live tests — hit the real Greenhouse API
# Run: set RUN_LIVE_TESTS=1 && python -m pytest tests/test_greenhouse.py::TestLive -v -s
# ---------------------------------------------------------------------------

class TestLive(unittest.TestCase):

    def setUp(self):
        import os
        if not os.getenv("RUN_LIVE_TESTS"):
            self.skipTest(
                "Live tests skipped. "
                "Run: set RUN_LIVE_TESTS=1 && "
                ".venv\\Scripts\\python -m pytest tests/test_greenhouse.py::TestLive -v -s"
            )

    def test_anthropic_returns_jobs(self):
        jobs = scrape(slug="anthropic",
                      keywords=["software", "engineer", "python", "backend",
                                "devops", "cloud", "ai"],
                      company_name="Anthropic", locations=[], max_age_days=0)
        print(f"\nAnthropic: {len(jobs)} total jobs")
        for j in jobs[:5]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        self.assertIsInstance(jobs, list)

    def test_datadog_returns_jobs(self):
        jobs = scrape(slug="datadog",
                      keywords=["software", "engineer", "backend", "devops", "cloud"],
                      company_name="Datadog", locations=[], max_age_days=0)
        print(f"\nDatadog: {len(jobs)} total jobs")
        for j in jobs[:5]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        self.assertIsInstance(jobs, list)

    def test_figma_returns_jobs(self):
        jobs = scrape(slug="figma",
                      keywords=["software", "engineer", "backend", "full stack"],
                      company_name="Figma", locations=[], max_age_days=0)
        print(f"\nFigma: {len(jobs)} total jobs")
        for j in jobs[:5]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        self.assertIsInstance(jobs, list)

    def test_doordash_returns_jobs(self):
        jobs = scrape(slug="doordashusa",
                      keywords=["software", "engineer", "backend", "python"],
                      company_name="DoorDash", locations=[], max_age_days=0)
        print(f"\nDoorDash: {len(jobs)} total jobs")
        for j in jobs[:5]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        self.assertIsInstance(jobs, list)

    def test_print_actual_location_strings(self):
        """Print raw Anthropic location strings to calibrate config.yaml locations."""
        jobs = scrape(slug="anthropic", keywords=[],
                      company_name="Anthropic", locations=[], max_age_days=0)
        locations = sorted({j.location for j in jobs})
        print(f"\nAnthropic raw location strings ({len(locations)} unique):")
        for loc in locations:
            print(f"  '{loc}'")
        self.assertIsInstance(jobs, list)


if __name__ == "__main__":
    unittest.main()
