"""
tests/test_ashby.py

Tests for scrapers/ashby.py.

All HTTP calls are mocked — tests run instantly and offline.
Fake API responses mirror the real Ashby public posting API shape.

Run with:  python -m pytest tests/test_ashby.py -v
Live tests: set RUN_LIVE_TESTS=1 && .venv\Scripts\python -m pytest tests/test_ashby.py::TestLive -v -s
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scrapers import Job
from scrapers.ashby import (
    _parse_ashby_date,
    _build_location,
    _keyword_match,
    _location_match,
    _fetch_jobs,
    scrape,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers — mirror the real Ashby API response shape
# ---------------------------------------------------------------------------

def _make_api_response(jobs: list, ok: bool = True) -> MagicMock:
    r = MagicMock()
    r.ok = ok
    r.json.return_value = {"apiVersion": "1", "jobs": jobs}
    return r


def _make_job_item(
    title: str = "Software Engineer",
    location: str = "San Francisco, CA",
    days_old: int = 0,
    is_remote: bool = False,
    workplace_type: str = "OnSite",
    secondary_locations: list = None,
    is_listed: bool = True,
    slug: str = "testco",
    job_id: str = "abc-123",
) -> dict:
    """Build a fake Ashby job dict matching the real public API shape."""
    dt = _utcnow() - timedelta(days=days_old)
    return {
        "title":              title,
        "location":           location,
        "secondaryLocations": secondary_locations or [],
        "department":         "Engineering",
        "isListed":           is_listed,
        "isRemote":           is_remote,
        "workplaceType":      workplace_type,
        "publishedAt":        dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "employmentType":     "FullTime",
        "jobUrl":             f"https://jobs.ashbyhq.com/{slug}/{job_id}",
        "applyUrl":           f"https://jobs.ashbyhq.com/{slug}/{job_id}/application",
    }


# ---------------------------------------------------------------------------
# _parse_ashby_date
# ---------------------------------------------------------------------------

class TestParseAshbyDate(unittest.TestCase):

    def test_z_suffix(self):
        dt = _parse_ashby_date("2026-06-15T10:00:00.000Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_explicit_offset(self):
        dt = _parse_ashby_date("2026-06-15T10:00:00+00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)

    def test_result_is_timezone_aware(self):
        dt = _parse_ashby_date("2026-06-15T10:00:00.000Z")
        self.assertIsNotNone(dt.tzinfo)

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_ashby_date(""))

    def test_none_returns_none(self):
        self.assertIsNone(_parse_ashby_date(None))

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_ashby_date("not-a-date"))


# ---------------------------------------------------------------------------
# _build_location
# ---------------------------------------------------------------------------

class TestBuildLocation(unittest.TestCase):

    def test_primary_only(self):
        item = {"location": "San Francisco, CA", "secondaryLocations": [],
                "isRemote": False, "workplaceType": "OnSite"}
        self.assertEqual(_build_location(item), "San Francisco, CA")

    def test_remote_flag_appends_remote(self):
        item = {"location": "San Francisco, CA", "secondaryLocations": [],
                "isRemote": True, "workplaceType": "Remote"}
        result = _build_location(item)
        self.assertIn("Remote", result)

    def test_hybrid_appends_hybrid(self):
        item = {"location": "New York, NY", "secondaryLocations": [],
                "isRemote": False, "workplaceType": "Hybrid"}
        result = _build_location(item)
        self.assertIn("Hybrid", result)

    def test_secondary_locations_included(self):
        item = {
            "location": "San Francisco, CA",
            "secondaryLocations": [{"location": "New York, NY"}],
            "isRemote": False,
            "workplaceType": "OnSite",
        }
        result = _build_location(item)
        self.assertIn("San Francisco, CA", result)
        self.assertIn("New York, NY", result)

    def test_secondary_with_address_fallback(self):
        item = {
            "location": "San Francisco, CA",
            "secondaryLocations": [
                {"location": "",
                 "address": {"addressLocality": "Austin",
                             "addressRegion": "Texas",
                             "addressCountry": "USA"}}
            ],
            "isRemote": False,
            "workplaceType": "OnSite",
        }
        result = _build_location(item)
        self.assertIn("Austin", result)

    def test_no_duplicate_remote(self):
        # "Remote" in primary + isRemote=True should not appear twice
        item = {"location": "Remote", "secondaryLocations": [],
                "isRemote": True, "workplaceType": "Remote"}
        result = _build_location(item)
        self.assertEqual(result.count("Remote"), 1)

    def test_empty_fields(self):
        item = {"location": "", "secondaryLocations": [],
                "isRemote": False, "workplaceType": ""}
        self.assertEqual(_build_location(item), "")


# ---------------------------------------------------------------------------
# _keyword_match / _location_match (same logic as greenhouse, quick sanity)
# ---------------------------------------------------------------------------

class TestFilters(unittest.TestCase):

    def test_keyword_match(self):
        self.assertTrue(_keyword_match("Software Engineer", ["software"]))
        self.assertFalse(_keyword_match("Accountant", ["software"]))
        self.assertTrue(_keyword_match("Anything", []))

    def test_location_match(self):
        self.assertTrue(_location_match("San Francisco, CA", ["San Francisco"]))
        self.assertFalse(_location_match("Tel Aviv, Israel", ["San Francisco", "Remote"]))
        self.assertTrue(_location_match("Tel Aviv, Israel", []))


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
        result = _fetch_jobs("testco", self._mock_session(_make_api_response(jobs)))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Software Engineer")

    def test_returns_empty_on_http_error(self):
        result = _fetch_jobs("testco", self._mock_session(
            _make_api_response([], ok=False)))
        self.assertEqual(result, [])

    def test_returns_empty_on_exception(self):
        s = MagicMock()
        s.get.side_effect = Exception("timeout")
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
        return patch("scrapers.ashby._fetch_jobs", return_value=jobs)

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

    def test_unlisted_jobs_excluded(self):
        fake = [
            _make_job_item("Software Engineer", "Remote", is_listed=True),
            _make_job_item("Internal Role", "Remote", is_listed=False),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Software Engineer")

    def test_keyword_filter(self):
        fake = [
            _make_job_item("Software Engineer", "Remote"),
            _make_job_item("Accountant", "Remote"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["software", "engineer"],
                          company_name="TestCo", locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Software Engineer")

    def test_seniority_filter(self):
        fake = [
            _make_job_item("Software Engineer", "Remote"),
            _make_job_item("Senior Software Engineer", "Remote"),
            _make_job_item("Staff Engineer", "Remote"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        titles = [j.title for j in jobs]
        self.assertIn("Software Engineer", titles)
        self.assertNotIn("Senior Software Engineer", titles)
        self.assertNotIn("Staff Engineer", titles)

    def test_location_filter_remote(self):
        """isRemote=True jobs should match locations: [Remote]"""
        fake = [
            _make_job_item("Software Engineer", "San Francisco, CA",
                           is_remote=False, workplace_type="OnSite"),
            _make_job_item("Software Engineer", "Tel Aviv, Israel",
                           is_remote=False, workplace_type="OnSite"),
            _make_job_item("Software Engineer", "",
                           is_remote=True, workplace_type="Remote"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo",
                          locations=["San Francisco", "Remote"],
                          max_age_days=0)
        self.assertEqual(len(jobs), 2)
        locations = [j.location for j in jobs]
        self.assertFalse(any("Israel" in l for l in locations))

    def test_age_filter_drops_old(self):
        fake = [
            _make_job_item("Software Engineer", "Remote", days_old=0),
            _make_job_item("Software Engineer", "Remote", days_old=5,
                           job_id="old-job"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=1)
        self.assertEqual(len(jobs), 1)

    def test_age_filter_zero_keeps_all(self):
        fake = [
            _make_job_item("Software Engineer", "Remote", days_old=0),
            _make_job_item("Software Engineer", "Remote", days_old=30,
                           job_id="old-job"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 2)

    def test_publishedat_used_not_updatedat(self):
        """Ashby uses publishedAt — verify the date field is populated."""
        fake = [_make_job_item("Software Engineer", "Remote", days_old=0)]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        self.assertIsNotNone(jobs[0].posted_dt)
        self.assertIsNotNone(jobs[0].posted_text)
        # posted_text is a date string e.g. "2026-06-15"
        self.assertRegex(jobs[0].posted_text, r"\d{4}-\d{2}-\d{2}")

    def test_never_raises(self):
        with patch("scrapers.ashby._fetch_jobs", side_effect=Exception("boom")):
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
# Live tests — hit the real Ashby API
# Run: set RUN_LIVE_TESTS=1 && .venv\Scripts\python -m pytest tests/test_ashby.py::TestLive -v -s
# ---------------------------------------------------------------------------

class TestLive(unittest.TestCase):

    def setUp(self):
        import os
        if not os.getenv("RUN_LIVE_TESTS"):
            self.skipTest(
                "Live tests skipped. "
                "Run: set RUN_LIVE_TESTS=1 && "
                ".venv\\Scripts\\python -m pytest tests/test_ashby.py::TestLive -v -s"
            )

    def test_cohere_returns_jobs(self):
        """Cohere is confirmed on Ashby — slug verified."""
        jobs = scrape(
            slug="cohere",
            keywords=["software", "engineer", "backend", "python", "devops",
                      "cloud", "ai", "ml", "full stack"],
            company_name="Cohere",
            locations=[],
            max_age_days=0,
        )
        print(f"\nCohere: {len(jobs)} total jobs")
        for j in jobs[:5]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        self.assertIsInstance(jobs, list)

    def test_cohere_print_location_strings(self):
        """Print all unique location strings to calibrate config-ashby.yaml."""
        jobs = scrape(
            slug="cohere",
            keywords=[],
            company_name="Cohere",
            locations=[],
            max_age_days=0,
        )
        locations = sorted({j.location for j in jobs})
        print(f"\nCohere raw location strings ({len(locations)} unique):")
        for loc in locations:
            print(f"  '{loc}'")
        self.assertIsInstance(jobs, list)

    def test_cohere_usa_filter(self):
        """Verify USA location filter works correctly on real Cohere data."""
        all_jobs = scrape(slug="cohere", keywords=[], company_name="Cohere",
                          locations=[], max_age_days=0)
        us_jobs = scrape(slug="cohere", keywords=[], company_name="Cohere",
                         locations=["United States", "USA", "San Francisco",
                                    "New York", "Remote"],
                         max_age_days=0)
        print(f"\nCohere: {len(all_jobs)} total, {len(us_jobs)} US/Remote")
        self.assertLessEqual(len(us_jobs), len(all_jobs))

    def test_publishedat_is_real_date(self):
        """Confirm Ashby returns real publishedAt timestamps (not None)."""
        jobs = scrape(slug="cohere", keywords=[], company_name="Cohere",
                      locations=[], max_age_days=0)
        if not jobs:
            self.skipTest("No jobs returned — company may have no openings")
        jobs_with_date = [j for j in jobs if j.posted_dt is not None]
        pct = len(jobs_with_date) / len(jobs) * 100
        print(f"\nCohere: {len(jobs_with_date)}/{len(jobs)} jobs have publishedAt ({pct:.0f}%)")
        # At least 80% of jobs should have a date
        self.assertGreater(pct, 80,
            "Fewer than 80% of jobs have publishedAt — check API response")


if __name__ == "__main__":
    unittest.main()
