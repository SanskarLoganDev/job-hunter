"""
tests/test_workable.py

Tests for scrapers/workable.py.

All HTTP calls are mocked — tests run instantly and offline.
Fake responses mirror the real Workable widget API response shape.

Run with:  python -m pytest tests/test_workable.py -v
Live tests: set RUN_LIVE_TESTS=1 && .venv\Scripts\python -m pytest tests/test_workable.py::TestLive -v -s
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scrapers import Job
from scrapers.workable import (
    _parse_workable_date,
    _keyword_match,
    _location_allowed,
    _fetch_jobs,
    scrape,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers — mirror the real Workable widget API response shape
# ---------------------------------------------------------------------------

def _make_api_response(jobs: list, ok: bool = True) -> MagicMock:
    r = MagicMock()
    r.ok = ok
    r.json.return_value = {
        "account": {"name": "TestCo", "url": "https://apply.workable.com/testco"},
        "jobs": jobs,
    }
    return r


def _make_job_item(
    title: str = "Software Engineer",
    city: str = "San Francisco",
    region: str = "California",
    country: str = "United States",
    country_code: str = "US",
    telecommuting: bool = False,
    remote: bool = False,
    days_old: int = 0,
    slug: str = "testco",
    job_id: str = "ABC123",
) -> dict:
    """Build a fake Workable job dict matching the real widget API shape."""
    dt = _utcnow() - timedelta(days=days_old)
    loc_str = f"{city}, {region}, {country}" if city else ""
    return {
        "id":              job_id,
        "title":           title,
        "shortlink":       f"https://apply.workable.com/{slug}/j/{job_id}/",
        "url":             f"https://apply.workable.com/{slug}/jobs/{job_id}",
        "application_url": f"https://apply.workable.com/{slug}/j/{job_id}/apply/",
        "created_at":      dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "employment_type": "full-time",
        "department":      "Engineering",
        "remote":          remote,
        "location": {
            "location_str": loc_str,
            "country":      country,
            "country_code": country_code,
            "region":       region,
            "region_code":  "CA",
            "city":         city,
            "zip_code":     "94105",
            "telecommuting": telecommuting,
        } if city else None,
    }


def _make_remote_job(title: str = "Software Engineer", days_old: int = 0,
                     job_id: str = "REM001") -> dict:
    """Build a remote job with no specific city."""
    dt = _utcnow() - timedelta(days=days_old)
    return {
        "id":              job_id,
        "title":           title,
        "shortlink":       f"https://apply.workable.com/testco/j/{job_id}/",
        "url":             f"https://apply.workable.com/testco/jobs/{job_id}",
        "application_url": f"https://apply.workable.com/testco/j/{job_id}/apply/",
        "created_at":      dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "employment_type": "full-time",
        "department":      "Engineering",
        "remote":          True,
        "location":        None,
    }


# ---------------------------------------------------------------------------
# _parse_workable_date
# ---------------------------------------------------------------------------

class TestParseWorkableDate(unittest.TestCase):

    def test_z_suffix(self):
        dt = _parse_workable_date("2026-06-15T10:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_result_is_timezone_aware(self):
        dt = _parse_workable_date("2026-06-15T10:00:00Z")
        self.assertIsNotNone(dt.tzinfo)

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_workable_date(""))

    def test_none_returns_none(self):
        self.assertIsNone(_parse_workable_date(None))

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_workable_date("not-a-date"))


# ---------------------------------------------------------------------------
# _keyword_match
# ---------------------------------------------------------------------------

class TestKeywordMatch(unittest.TestCase):

    def test_match(self):
        self.assertTrue(_keyword_match("Software Engineer", ["software"]))

    def test_no_match(self):
        self.assertFalse(_keyword_match("Accountant", ["software"]))

    def test_empty_keywords_always_matches(self):
        self.assertTrue(_keyword_match("Anything", []))

    def test_case_insensitive(self):
        self.assertTrue(_keyword_match("PYTHON DEVELOPER", ["python"]))


# ---------------------------------------------------------------------------
# _location_allowed
# ---------------------------------------------------------------------------

class TestLocationAllowed(unittest.TestCase):

    def _us_job(self) -> dict:
        return _make_job_item("SWE", "San Francisco", "California", "United States", "US")

    def _intl_job(self) -> dict:
        return _make_job_item("SWE", "Tel Aviv", "Tel Aviv", "Israel", "IL")

    def _remote_job(self) -> dict:
        return _make_remote_job()

    def _telecommute_job(self) -> dict:
        return _make_job_item("SWE", "New York", "New York", "United States", "US",
                              telecommuting=True)

    def test_us_code_matches_us(self):
        self.assertTrue(_location_allowed(self._us_job(), ["US"]))

    def test_us_code_matches_usa(self):
        self.assertTrue(_location_allowed(self._us_job(), ["USA"]))

    def test_us_code_matches_united_states(self):
        self.assertTrue(_location_allowed(self._us_job(), ["United States"]))

    def test_intl_blocked_by_us_filter(self):
        self.assertFalse(_location_allowed(self._intl_job(), ["US"]))

    def test_remote_matches_remote(self):
        self.assertTrue(_location_allowed(self._remote_job(), ["Remote"]))

    def test_remote_not_matched_by_us_filter(self):
        # Remote jobs with no location object should NOT match "US"
        self.assertFalse(_location_allowed(self._remote_job(), ["US"]))

    def test_us_and_remote_matches_both(self):
        self.assertTrue(_location_allowed(self._us_job(), ["US", "Remote"]))
        self.assertTrue(_location_allowed(self._remote_job(), ["US", "Remote"]))

    def test_telecommuting_matches_remote(self):
        self.assertTrue(_location_allowed(self._telecommute_job(), ["Remote"]))

    def test_city_match(self):
        self.assertTrue(_location_allowed(self._us_job(), ["San Francisco"]))

    def test_empty_allowed_passes_everything(self):
        self.assertTrue(_location_allowed(self._intl_job(), []))


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
        r.json.return_value = {"account": {"name": "TestCo"}}
        self.assertEqual(_fetch_jobs("testco", self._mock_session(r)), [])


# ---------------------------------------------------------------------------
# scrape()
# ---------------------------------------------------------------------------

class TestScrape(unittest.TestCase):

    def _patch_fetch(self, jobs: list):
        return patch("scrapers.workable._fetch_jobs", return_value=jobs)

    def test_returns_job_objects(self):
        fake = [_make_job_item("Software Engineer", days_old=0)]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["software"],
                          company_name="TestCo", locations=["US"], max_age_days=1)
        self.assertEqual(len(jobs), 1)
        self.assertIsInstance(jobs[0], Job)

    def test_job_fields_populated(self):
        fake = [_make_job_item("Software Engineer", "New York", "New York",
                               "United States", "US", days_old=0, job_id="NY001")]
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

    def test_keyword_filter(self):
        fake = [
            _make_job_item("Software Engineer", days_old=0),
            _make_job_item("Accountant", days_old=0, job_id="ACCT001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=["software", "engineer"],
                          company_name="TestCo", locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Software Engineer")

    def test_seniority_filter(self):
        fake = [
            _make_job_item("Software Engineer", days_old=0),
            _make_job_item("Senior Software Engineer", days_old=0, job_id="SR001"),
            _make_job_item("Staff Engineer", days_old=0, job_id="STAFF001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        titles = [j.title for j in jobs]
        self.assertIn("Software Engineer", titles)
        self.assertNotIn("Senior Software Engineer", titles)
        self.assertNotIn("Staff Engineer", titles)

    def test_location_filter_us_only(self):
        fake = [
            _make_job_item("Software Engineer", "San Francisco", "California",
                           "United States", "US", days_old=0),
            _make_job_item("Software Engineer", "Tel Aviv", "Tel Aviv",
                           "Israel", "IL", days_old=0, job_id="IL001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo", locations=["US"], max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertNotIn("Israel", jobs[0].location)

    def test_remote_jobs_included_when_remote_in_locations(self):
        fake = [
            _make_job_item("Software Engineer", "San Francisco", "California",
                           "United States", "US", days_old=0),
            _make_remote_job("Software Engineer", days_old=0),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[],
                          company_name="TestCo", locations=["US", "Remote"],
                          max_age_days=0)
        self.assertEqual(len(jobs), 2)

    def test_age_filter_drops_old(self):
        fake = [
            _make_job_item("Software Engineer", days_old=0),
            _make_job_item("Software Engineer", days_old=5, job_id="OLD001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=1)
        self.assertEqual(len(jobs), 1)

    def test_age_filter_zero_keeps_all(self):
        fake = [
            _make_job_item("Software Engineer", days_old=0),
            _make_job_item("Software Engineer", days_old=30, job_id="OLD001"),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        self.assertEqual(len(jobs), 2)

    def test_never_raises(self):
        with patch("scrapers.workable._fetch_jobs", side_effect=Exception("boom")):
            jobs = scrape(slug="testco", keywords=["software"],
                          company_name="TestCo")
        self.assertEqual(jobs, [])

    def test_uid_stable_across_runs(self):
        fake = [_make_job_item("Software Engineer", days_old=0, job_id="STABLE001")]
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

    def test_remote_flag_appended_to_location_string(self):
        """telecommuting=True should add '; Remote' to the location string."""
        fake = [_make_job_item("Software Engineer", "Austin", "Texas",
                               "United States", "US", telecommuting=True, days_old=0)]
        with self._patch_fetch(fake):
            jobs = scrape(slug="testco", keywords=[], company_name="TestCo",
                          locations=[], max_age_days=0)
        self.assertIn("Remote", jobs[0].location)


# ---------------------------------------------------------------------------
# Live tests — hit the real Workable API
# Run: set RUN_LIVE_TESTS=1 && .venv\Scripts\python -m pytest tests/test_workable.py::TestLive -v -s
# ---------------------------------------------------------------------------

class TestLive(unittest.TestCase):

    def setUp(self):
        import os
        if not os.getenv("RUN_LIVE_TESTS"):
            self.skipTest(
                "Live tests skipped. "
                r"Run: set RUN_LIVE_TESTS=1 && "
                r".venv\Scripts\python -m pytest tests/test_workable.py::TestLive -v -s"
            )

    def _run(self, slug: str, name: str):
        jobs = scrape(
            slug=slug,
            keywords=["software", "engineer", "developer", "backend",
                      "full stack", "devops", "cloud", "python", "ai"],
            company_name=name,
            locations=[],      # no filter — see everything
            max_age_days=0,    # no age filter
        )
        print(f"\n{name} ({slug}): {len(jobs)} jobs after keyword+seniority filter")
        for j in jobs[:5]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        return jobs

    def test_print_slug_guidance(self):
        """
        Workable slug = the subdomain at apply.workable.com/{slug}.
        This test just prints guidance — no assertion.
        """
        print("\n=== Workable slug finder ===")
        print("Go to: https://apply.workable.com/{slug}")
        print("If the page loads with jobs, that slug is correct.")
        print("Examples to try: typeform, intercom, netlify, discord")

    def test_typeform(self):
        """Typeform is a well-known Workable customer."""
        jobs = self._run("typeform", "Typeform")
        self.assertIsInstance(jobs, list)

    def test_print_location_strings(self):
        """Print raw location strings to calibrate config-workable.yaml."""
        jobs = scrape(
            slug="typeform",
            keywords=[],
            company_name="Typeform",
            locations=[],
            max_age_days=0,
        )
        locs = sorted({j.location for j in jobs})
        print(f"\nTypeform raw location strings ({len(locs)} unique):")
        for l in locs:
            print(f"  {repr(l)}")
        self.assertIsInstance(jobs, list)


if __name__ == "__main__":
    unittest.main()
