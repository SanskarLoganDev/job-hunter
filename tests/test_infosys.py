"""
tests/test_infosys.py

Tests for scrapers/infosys.py.

All HTTP calls are mocked — tests run offline.
"""

import unittest
from unittest.mock import MagicMock, patch

from scrapers import Job
from scrapers.infosys import (
    _fetch_jobs,
    _keyword_match,
    _location_match,
    _parse_job_cards,
    scrape,
)


def _html(cards: str) -> str:
    return f"<html><body>{cards}</body></html>"


def _card(
    title: str = "Cloud Engineer",
    reqid: str = "151838BR",
    location: str = "Richardson, TX",
    country: str = "USA",
) -> str:
    return f"""
    <a href="https://digitalcareers.infosys.com/global-careers/company-job/description/reqid/{reqid}"
       class="job editable-cursor">
      <div class="left-section">
        <div class="job-title" data-title="{title}">{title}</div>
        <div class="job-location js-job-city">
          <div class="location-inline">{location}</div>
          <div class="location-inline">&nbsp;-</div>
          <div class="location-inline">{country}</div>
        </div>
        <div class="job-description js-job-reqid">
          <div class="location-inline">{reqid}</div>
        </div>
      </div>
    </a>
    """


class TestParseJobCards(unittest.TestCase):

    def test_parses_infosys_card(self):
        jobs = _parse_job_cards(_html(_card()))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Cloud Engineer")
        self.assertEqual(jobs[0]["reqid"], "151838BR")
        self.assertEqual(jobs[0]["location"], "Richardson, TX, USA")
        self.assertEqual(
            jobs[0]["link"],
            "https://digitalcareers.infosys.com/global-careers/company-job/description/reqid/151838BR",
        )

    def test_relative_link_becomes_absolute(self):
        html = """
        <a href="/global-careers/company-job/description/reqid/123BR" class="job">
          <div class="job-title" data-title="Software Engineer">Software Engineer</div>
          <div class="job-location"><div class="location-inline">Austin, TX</div></div>
        </a>
        """

        jobs = _parse_job_cards(_html(html))

        self.assertEqual(
            jobs[0]["link"],
            "https://digitalcareers.infosys.com/global-careers/company-job/description/reqid/123BR",
        )
        self.assertEqual(jobs[0]["reqid"], "123BR")

    def test_skips_cards_without_title(self):
        html = """
        <a href="/global-careers/company-job/description/reqid/123BR" class="job">
          <div class="job-location"><div class="location-inline">Austin, TX</div></div>
        </a>
        """

        self.assertEqual(_parse_job_cards(_html(html)), [])


class TestFilters(unittest.TestCase):

    def test_keyword_match(self):
        self.assertTrue(_keyword_match("Java Fullstack Developer", ["full stack", "developer"]))
        self.assertFalse(_keyword_match("Project Manager", ["software engineer"]))

    def test_location_match_uses_shared_us_rules(self):
        self.assertTrue(_location_match("Richardson, TX, USA", ["United States"]))
        self.assertTrue(_location_match("Remote, India", ["Remote"]))
        self.assertFalse(_location_match("London, United Kingdom", ["United States", "Remote"]))


class TestFetchJobs(unittest.TestCase):

    def test_fetches_until_short_page(self):
        session = MagicMock()
        r1 = MagicMock(ok=True, text=_html(_card("Cloud Engineer", "1BR")))
        session.get.return_value = r1

        jobs = _fetch_jobs(session, max_pages=3, per_page=100, location_param="USA")

        self.assertEqual(len(jobs), 1)
        session.get.assert_called_once()

    def test_returns_empty_on_http_error(self):
        session = MagicMock()
        session.get.return_value = MagicMock(ok=False, text="")

        self.assertEqual(_fetch_jobs(session), [])

    def test_deduplicates_links_across_pages(self):
        session = MagicMock()
        full_page = _html(_card("Cloud Engineer", "1BR"))
        r1 = MagicMock(ok=True, text=full_page)
        r2 = MagicMock(ok=True, text=full_page)
        session.get.side_effect = [r1, r2]

        jobs = _fetch_jobs(session, max_pages=2, per_page=1, location_param="USA")

        self.assertEqual(len(jobs), 1)


class TestScrape(unittest.TestCase):

    def _patch_fetch(self, jobs: list):
        return patch("scrapers.infosys._fetch_jobs", return_value=jobs)

    def test_returns_job_objects(self):
        raw = [{
            "title": "Cloud Engineer",
            "location": "Richardson, TX, USA",
            "reqid": "151838BR",
            "link": "https://digitalcareers.infosys.com/global-careers/company-job/description/reqid/151838BR",
        }]

        with self._patch_fetch(raw):
            jobs = scrape(
                slug="infosys",
                keywords=["cloud engineer"],
                company_name="Infosys",
                locations=["United States"],
                max_age_days=1,
            )

        self.assertEqual(len(jobs), 1)
        self.assertIsInstance(jobs[0], Job)
        self.assertEqual(jobs[0].title, "Cloud Engineer")
        self.assertEqual(jobs[0].posted_text, "reqid 151838BR")
        self.assertIsNone(jobs[0].posted_dt)

    def test_filters_keyword_seniority_and_location(self):
        raw = [
            {
                "title": "Cloud Engineer",
                "location": "Richardson, TX, USA",
                "reqid": "1BR",
                "link": "https://digitalcareers.infosys.com/global-careers/company-job/description/reqid/1BR",
            },
            {
                "title": "Senior Cloud Engineer",
                "location": "Richardson, TX, USA",
                "reqid": "2BR",
                "link": "https://digitalcareers.infosys.com/global-careers/company-job/description/reqid/2BR",
            },
            {
                "title": "Accountant",
                "location": "Richardson, TX, USA",
                "reqid": "3BR",
                "link": "https://digitalcareers.infosys.com/global-careers/company-job/description/reqid/3BR",
            },
            {
                "title": "Cloud Engineer",
                "location": "London, United Kingdom",
                "reqid": "4BR",
                "link": "https://digitalcareers.infosys.com/global-careers/company-job/description/reqid/4BR",
            },
        ]

        with self._patch_fetch(raw):
            jobs = scrape(
                slug="infosys",
                keywords=["cloud engineer"],
                company_name="Infosys",
                locations=["United States"],
                max_age_days=1,
            )

        self.assertEqual([job.posted_text for job in jobs], ["reqid 1BR"])


if __name__ == "__main__":
    unittest.main()
