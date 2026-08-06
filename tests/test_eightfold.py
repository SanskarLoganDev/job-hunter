r"""
tests/test_eightfold.py

Tests for scrapers/eightfold.py (generic Eightfold AI scraper — covers
Microsoft, CBTS, and any future Eightfold-based tenant via config).

All HTTP calls are mocked — tests run instantly and offline.
Fake responses mirror the real Eightfold pcsx/search API shape exactly
(confirmed live against both apply.careers.microsoft.com and jobs.cbts.com).

Run with:  python -m pytest tests/test_eightfold.py -v
Live tests: set RUN_LIVE_TESTS=1 && .venv\Scripts\python -m pytest tests/test_eightfold.py::TestLive -v -s
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scrapers import Job
from scrapers.eightfold import (
    _parse_ts,
    _build_location,
    _keyword_match,
    _fetch_all,
    scrape,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_ts(dt: datetime) -> int:
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# Helpers — mirror the real Eightfold pcsx/search API response shape
# ---------------------------------------------------------------------------

def _make_api_response(positions: list, count: int = None, ok: bool = True) -> MagicMock:
    r = MagicMock()
    r.ok = ok
    r.json.return_value = {
        "status": 200,
        "data": {
            "count": count if count is not None else len(positions),
            "positions": positions,
        },
    }
    return r


def _make_position(
    title: str = "Software Engineer",
    std_locations: list = None,
    days_old: int = 0,
    work_location_option: str = "onsite",
    pos_id: int = 1443152540993,
) -> dict:
    """Build a fake Eightfold position dict matching the real API shape."""
    dt = _utcnow() - timedelta(days=days_old)
    return {
        "id":                   pos_id,
        "name":                 title,
        "locations":            std_locations or ["Cincinnati, OH"],
        "standardizedLocations": std_locations or ["Cincinnati, OH, US"],
        "postedTs":             _to_ts(dt),
        "workLocationOption":   work_location_option,
        "positionUrl":          f"/careers/job/{pos_id}",
    }


# ---------------------------------------------------------------------------
# _parse_ts
# ---------------------------------------------------------------------------

class TestParseTs(unittest.TestCase):

    def test_seconds_timestamp(self):
        ts = int(datetime(2026, 6, 15, tzinfo=timezone.utc).timestamp())
        dt = _parse_ts(ts)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_none_returns_none(self):
        self.assertIsNone(_parse_ts(None))

    def test_string_seconds_also_works(self):
        ts = int(datetime(2026, 6, 15, tzinfo=timezone.utc).timestamp())
        dt = _parse_ts(str(ts))
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_ts("not-a-number"))


# ---------------------------------------------------------------------------
# _build_location
# ---------------------------------------------------------------------------

class TestBuildLocation(unittest.TestCase):

    def test_plain_onsite(self):
        loc = _build_location({
            "standardizedLocations": ["Cincinnati, OH, US"],
            "workLocationOption": "onsite",
        })
        self.assertEqual(loc, "Cincinnati, OH, US")

    def test_hybrid_appended(self):
        loc = _build_location({
            "standardizedLocations": ["Cincinnati, OH, US"],
            "workLocationOption": "hybrid",
        })
        self.assertIn("Hybrid", loc)

    def test_remote_local_appended(self):
        # CBTS uses "remote_local" (not Microsoft's plain "remote")
        loc = _build_location({
            "standardizedLocations": ["OH, US"],
            "workLocationOption": "remote_local",
        })
        self.assertIn("Remote", loc)

    def test_remote_global_appended(self):
        loc = _build_location({
            "standardizedLocations": ["US"],
            "workLocationOption": "remote_global",
        })
        self.assertIn("Remote", loc)

    def test_plain_remote_appended(self):
        # Microsoft's convention
        loc = _build_location({
            "standardizedLocations": ["Redmond, WA, US"],
            "workLocationOption": "remote",
        })
        self.assertIn("Remote", loc)

    def test_caps_at_three_locations(self):
        loc = _build_location({
            "standardizedLocations": ["A, US", "B, US", "C, US", "D, US"],
            "workLocationOption": "onsite",
        })
        self.assertEqual(loc.count(";"), 2)  # 3 parts joined = 2 separators

    def test_no_locations(self):
        loc = _build_location({"standardizedLocations": [], "workLocationOption": "onsite"})
        self.assertEqual(loc, "")


# ---------------------------------------------------------------------------
# _keyword_match
# ---------------------------------------------------------------------------

class TestKeywordMatch(unittest.TestCase):

    def test_match(self):
        self.assertTrue(_keyword_match("Software Engineer", ["software"]))
        self.assertFalse(_keyword_match("Accountant", ["software"]))
        self.assertTrue(_keyword_match("Anything", []))


# ---------------------------------------------------------------------------
# _fetch_all
# ---------------------------------------------------------------------------

class TestFetchAll(unittest.TestCase):

    def _mock_session(self, response: MagicMock) -> MagicMock:
        s = MagicMock()
        s.get.return_value = response
        return s

    def test_returns_positions_on_success(self):
        positions = [_make_position("Software Engineer")]
        session = self._mock_session(_make_api_response(positions))
        result = _fetch_all("", session, "https://jobs.cbts.com", "cbts.com", "United States")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Software Engineer")

    def test_returns_empty_on_http_error(self):
        session = self._mock_session(_make_api_response([], ok=False))
        result = _fetch_all("", session, "https://jobs.cbts.com", "cbts.com", "United States")
        self.assertEqual(result, [])

    def test_returns_empty_on_exception(self):
        s = MagicMock()
        s.get.side_effect = Exception("timeout")
        result = _fetch_all("", s, "https://jobs.cbts.com", "cbts.com", "United States")
        self.assertEqual(result, [])

    def test_stops_pagination_when_exhausted(self):
        # count == len(positions) on page 1 -> no second page requested
        positions = [_make_position("Software Engineer", pos_id=1)]
        session = self._mock_session(_make_api_response(positions, count=1))
        result = _fetch_all("", session, "https://jobs.cbts.com", "cbts.com", "United States")
        self.assertEqual(len(result), 1)
        self.assertEqual(session.get.call_count, 1)


# ---------------------------------------------------------------------------
# scrape()
# ---------------------------------------------------------------------------

class TestScrape(unittest.TestCase):

    def _patch_fetch(self, positions: list):
        return patch("scrapers.eightfold._fetch_all", return_value=positions)

    def test_missing_domain_or_base_url_returns_empty(self):
        self.assertEqual(scrape(keywords=[], company_name="X"), [])
        self.assertEqual(scrape(keywords=[], company_name="X", domain="x.com"), [])
        self.assertEqual(scrape(keywords=[], company_name="X", base_url="https://x.com"), [])

    def test_returns_job_objects(self):
        fake = [_make_position("Software Engineer")]
        with self._patch_fetch(fake):
            jobs = scrape(keywords=["software"], company_name="CBTS",
                          domain="cbts.com", base_url="https://jobs.cbts.com",
                          max_age_days=1)
        self.assertEqual(len(jobs), 1)
        self.assertIsInstance(jobs[0], Job)

    def test_job_fields_populated(self):
        fake = [_make_position("Software Engineer", ["Cincinnati, OH, US"],
                               days_old=0, pos_id=999)]
        with self._patch_fetch(fake):
            jobs = scrape(keywords=["software"], company_name="CBTS",
                          domain="cbts.com", base_url="https://jobs.cbts.com",
                          max_age_days=0)
        j = jobs[0]
        self.assertEqual(j.title, "Software Engineer")
        self.assertEqual(j.company, "CBTS")
        self.assertEqual(j.link, "https://jobs.cbts.com/careers/job/999")
        self.assertIn("Cincinnati", j.location)
        self.assertIsNotNone(j.posted_dt)
        self.assertIsNotNone(j.posted_dt.tzinfo)
        self.assertRegex(j.posted_text, r"\d{4}-\d{2}-\d{2}")

    def test_keyword_filter(self):
        fake = [
            _make_position("Software Engineer", pos_id=1),
            _make_position("Accountant", pos_id=2),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(keywords=["software", "engineer"], company_name="CBTS",
                          domain="cbts.com", base_url="https://jobs.cbts.com",
                          max_age_days=0)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Software Engineer")

    def test_seniority_filter(self):
        fake = [
            _make_position("Software Engineer", pos_id=1),
            _make_position("Senior Engineer", pos_id=2),
            _make_position("Staff Engineer", pos_id=3),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(keywords=[], company_name="CBTS",
                          domain="cbts.com", base_url="https://jobs.cbts.com",
                          max_age_days=0)
        titles = [j.title for j in jobs]
        self.assertIn("Software Engineer", titles)
        self.assertNotIn("Senior Engineer", titles)
        self.assertNotIn("Staff Engineer", titles)

    def test_dedup_by_id(self):
        fake = [
            _make_position("Software Engineer", pos_id=1),
            _make_position("Software Engineer", pos_id=1),  # duplicate id
        ]
        with self._patch_fetch(fake):
            jobs = scrape(keywords=[], company_name="CBTS",
                          domain="cbts.com", base_url="https://jobs.cbts.com",
                          max_age_days=0)
        self.assertEqual(len(jobs), 1)

    def test_age_filter_drops_old(self):
        fake = [
            _make_position("Software Engineer", pos_id=1, days_old=0),
            _make_position("Software Engineer", pos_id=2, days_old=5),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(keywords=[], company_name="CBTS",
                          domain="cbts.com", base_url="https://jobs.cbts.com",
                          max_age_days=1)
        self.assertEqual(len(jobs), 1)

    def test_age_filter_zero_keeps_all(self):
        fake = [
            _make_position("Software Engineer", pos_id=1, days_old=0),
            _make_position("Software Engineer", pos_id=2, days_old=30),
        ]
        with self._patch_fetch(fake):
            jobs = scrape(keywords=[], company_name="CBTS",
                          domain="cbts.com", base_url="https://jobs.cbts.com",
                          max_age_days=0)
        self.assertEqual(len(jobs), 2)

    def test_never_raises(self):
        with patch("scrapers.eightfold._fetch_all", side_effect=Exception("boom")):
            jobs = scrape(keywords=["software"], company_name="CBTS",
                          domain="cbts.com", base_url="https://jobs.cbts.com")
        self.assertEqual(jobs, [])

    def test_uid_stable_across_runs(self):
        fake = [_make_position("Software Engineer", pos_id=42)]
        with self._patch_fetch(fake):
            jobs1 = scrape(keywords=[], company_name="CBTS",
                           domain="cbts.com", base_url="https://jobs.cbts.com",
                           max_age_days=0)
        with self._patch_fetch(fake):
            jobs2 = scrape(keywords=[], company_name="CBTS",
                           domain="cbts.com", base_url="https://jobs.cbts.com",
                           max_age_days=0)
        self.assertEqual({j.uid for j in jobs1}, {j.uid for j in jobs2})

    def test_empty_api_returns_empty(self):
        with self._patch_fetch([]):
            jobs = scrape(keywords=["software"], company_name="CBTS",
                          domain="cbts.com", base_url="https://jobs.cbts.com",
                          max_age_days=1)
        self.assertEqual(jobs, [])

    def test_two_tenants_produce_distinct_links(self):
        # Same position id, different tenants -> different links -> different uids
        ms_fake = [_make_position("Software Engineer", pos_id=100)]
        with self._patch_fetch(ms_fake):
            ms_jobs = scrape(keywords=[], company_name="Microsoft",
                             domain="microsoft.com",
                             base_url="https://apply.careers.microsoft.com",
                             max_age_days=0)
        cbts_fake = [_make_position("Software Engineer", pos_id=100)]
        with self._patch_fetch(cbts_fake):
            cbts_jobs = scrape(keywords=[], company_name="CBTS",
                               domain="cbts.com", base_url="https://jobs.cbts.com",
                               max_age_days=0)
        self.assertNotEqual(ms_jobs[0].link, cbts_jobs[0].link)
        self.assertNotEqual(ms_jobs[0].uid, cbts_jobs[0].uid)


# ---------------------------------------------------------------------------
# Live tests — hit the real Eightfold APIs for Microsoft and CBTS
# Run: set RUN_LIVE_TESTS=1 && .venv\Scripts\python -m pytest tests/test_eightfold.py::TestLive -v -s
# ---------------------------------------------------------------------------

class TestLive(unittest.TestCase):

    def setUp(self):
        import os
        if not os.getenv("RUN_LIVE_TESTS"):
            self.skipTest(
                "Live tests skipped. "
                r"Run: set RUN_LIVE_TESTS=1 && "
                r".venv\Scripts\python -m pytest tests/test_eightfold.py::TestLive -v -s"
            )

    def test_microsoft_returns_jobs(self):
        jobs = scrape(
            keywords=["software", "engineer", "cloud", "devops"],
            company_name="Microsoft",
            domain="microsoft.com",
            base_url="https://apply.careers.microsoft.com",
            location_param="United States, Multiple Locations, Multiple Locations",
            max_age_days=0,
        )
        print(f"\nMicrosoft: {len(jobs)} total jobs")
        for j in jobs[:5]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        self.assertIsInstance(jobs, list)

    def test_cbts_returns_jobs(self):
        jobs = scrape(
            keywords=[],  # no keyword filter — see everything CBTS has
            company_name="CBTS",
            domain="cbts.com",
            base_url="https://jobs.cbts.com",
            location_param="United States",
            max_age_days=0,
        )
        print(f"\nCBTS: {len(jobs)} total jobs")
        for j in jobs[:10]:
            print(f"  {j.title} | {j.location} | {j.posted_text}")
        self.assertIsInstance(jobs, list)

    def test_cbts_print_location_strings(self):
        jobs = scrape(
            keywords=[],
            company_name="CBTS",
            domain="cbts.com",
            base_url="https://jobs.cbts.com",
            location_param="United States",
            max_age_days=0,
        )
        locations = sorted({j.location for j in jobs})
        print(f"\nCBTS raw location strings ({len(locations)} unique):")
        for loc in locations:
            print(f"  '{loc}'")
        self.assertIsInstance(jobs, list)


if __name__ == "__main__":
    unittest.main()
