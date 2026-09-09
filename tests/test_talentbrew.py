"""
tests/test_talentbrew.py

Tests for scrapers/talentbrew.py.

All HTTP calls are mocked — tests run offline.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scrapers import Job
from scrapers.talentbrew import (
    _fetch_jobs,
    _keyword_match,
    _location_match,
    _parse_job_rows,
    _parse_tb_date,
    scrape,
)


def _date(days_old: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_old)).strftime("%m/%d/%Y")


def _html(rows: str) -> str:
    return f"<html><body><div id='search-results-list'><ul>{rows}</ul></div></body></html>"


def _row(
    title: str = "Software Engineer",
    job_id: str = "1001",
    location: str = "Irving, TX",
    posted: str | None = None,
    href: str | None = None,
) -> str:
    posted = posted or _date()
    href = href or f"/en/job/irving/software-engineer/733/{job_id}"
    return f"""
    <li>
      <a class="search-results__job-title-link" href="{href}" data-job-id="{job_id}">{title}</a>
      <span class="search-results__job-location">{location}</span>
      <span class="search-results__job-date-posted">{posted}</span>
      <button type="button" class="js-save-job-btn" data-job-id="{job_id}">
        <span>Save for Later</span>
      </button>
    </li>
    """


class TestParseTbDate(unittest.TestCase):

    def test_parses_mm_dd_yyyy_as_utc(self):
        dt = _parse_tb_date("09/04/2026")

        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 9)
        self.assertEqual(dt.day, 4)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_empty_or_invalid_returns_none(self):
        self.assertIsNone(_parse_tb_date(""))
        self.assertIsNone(_parse_tb_date("not-a-date"))


class TestParseJobRows(unittest.TestCase):

    def test_parses_title_link_location_date_and_job_id(self):
        jobs = _parse_job_rows(_html(_row()), "https://careers.example.com")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Software Engineer")
        self.assertEqual(jobs[0]["job_id"], "1001")
        self.assertEqual(jobs[0]["location"], "Irving, TX")
        self.assertEqual(jobs[0]["posted_text"], _date())
        self.assertEqual(
            jobs[0]["link"],
            "https://careers.example.com/en/job/irving/software-engineer/733/1001",
        )
        self.assertIsNotNone(jobs[0]["posted_dt"])

    def test_appends_location_facet_label_for_multiple(self):
        jobs = _parse_job_rows(
            _html(_row(location="Multiple")),
            "https://careers.example.com",
            location_label="Remote",
        )

        self.assertEqual(jobs[0]["location"], "Multiple; Remote")

    def test_skips_rows_without_title(self):
        html = """
        <li>
          <a class="search-results__job-title-link" href="/en/job/test/733/1" data-job-id="1"></a>
          <span class="search-results__job-location">Irving, TX</span>
        </li>
        """

        self.assertEqual(_parse_job_rows(_html(html), "https://careers.example.com"), [])


class TestFilters(unittest.TestCase):

    def test_keyword_match(self):
        self.assertTrue(_keyword_match("Java Full Stack Developer", ["full stack", "developer"]))
        self.assertFalse(_keyword_match("Project Manager", ["software engineer"]))

    def test_location_match_uses_shared_rules(self):
        self.assertTrue(_location_match("Columbus, OH", ["United States"]))
        self.assertTrue(_location_match("Multiple; Remote", ["Remote"]))
        self.assertFalse(_location_match("Cork, Munster", ["United States", "Remote"]))


class TestFetchJobs(unittest.TestCase):

    def test_fetches_multiple_location_facets_and_dedupes(self):
        session = MagicMock()
        session.get.side_effect = [
            MagicMock(ok=True, text=_html(_row(job_id="1", location="Irving, TX"))),
            MagicMock(ok=True, text=_html(_row(job_id="1", location="Multiple"))),
        ]

        jobs = _fetch_jobs(
            session=session,
            base_url="https://careers.example.com",
            search_path="/en/search-jobs",
            query_params={"acm": "ALL"},
            location_params=["6252001", "1000000000100"],
            location_param_labels={"6252001": "United States", "1000000000100": "Remote"},
            max_pages=1,
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(session.get.call_count, 2)

    def test_returns_empty_on_http_error(self):
        session = MagicMock()
        session.get.return_value = MagicMock(ok=False, text="")

        self.assertEqual(
            _fetch_jobs(
                session=session,
                base_url="https://careers.example.com",
                search_path="/en/search-jobs",
            ),
            [],
        )


class TestScrape(unittest.TestCase):

    def _patch_fetch(self, jobs: list):
        return patch("scrapers.talentbrew._fetch_jobs", return_value=jobs)

    def test_returns_job_objects(self):
        raw = [{
            "title": "Software Engineer",
            "location": "Irving, TX",
            "posted_text": _date(),
            "posted_dt": datetime.now(timezone.utc),
            "link": "https://careers.example.com/en/job/irving/software-engineer/733/1",
        }]

        with self._patch_fetch(raw):
            jobs = scrape(
                keywords=["software engineer"],
                company_name="McKesson",
                locations=["United States"],
                max_age_days=1,
                base_url="https://careers.example.com",
            )

        self.assertEqual(len(jobs), 1)
        self.assertIsInstance(jobs[0], Job)
        self.assertEqual(jobs[0].title, "Software Engineer")
        self.assertEqual(jobs[0].company, "McKesson")

    def test_filters_keyword_seniority_location_and_age(self):
        now = datetime.now(timezone.utc)
        raw = [
            {
                "title": "Software Engineer",
                "location": "Irving, TX",
                "posted_text": _date(),
                "posted_dt": now,
                "link": "https://careers.example.com/en/job/irving/software-engineer/733/1",
            },
            {
                "title": "Senior Software Engineer",
                "location": "Irving, TX",
                "posted_text": _date(),
                "posted_dt": now,
                "link": "https://careers.example.com/en/job/irving/software-engineer/733/2",
            },
            {
                "title": "Accountant",
                "location": "Irving, TX",
                "posted_text": _date(),
                "posted_dt": now,
                "link": "https://careers.example.com/en/job/irving/accountant/733/3",
            },
            {
                "title": "Software Engineer",
                "location": "Cork, Munster",
                "posted_text": _date(),
                "posted_dt": now,
                "link": "https://careers.example.com/en/job/cork/software-engineer/733/4",
            },
            {
                "title": "Software Engineer",
                "location": "Irving, TX",
                "posted_text": _date(days_old=5),
                "posted_dt": now - timedelta(days=5),
                "link": "https://careers.example.com/en/job/irving/software-engineer/733/5",
            },
        ]

        with self._patch_fetch(raw):
            jobs = scrape(
                keywords=["software engineer"],
                company_name="McKesson",
                locations=["United States"],
                max_age_days=1,
                base_url="https://careers.example.com",
            )

        self.assertEqual([job.link for job in jobs], [
            "https://careers.example.com/en/job/irving/software-engineer/733/1"
        ])

    def test_missing_base_url_returns_empty(self):
        self.assertEqual(
            scrape(
                keywords=["software engineer"],
                company_name="McKesson",
                locations=["United States"],
                base_url="",
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
