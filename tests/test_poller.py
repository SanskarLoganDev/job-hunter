"""
tests/test_poller.py

Tests for poller.py config default merging.

No scraper or network calls.
"""

import unittest
from unittest.mock import MagicMock, patch

import poller


class TestConfigDefaults(unittest.TestCase):

    def test_apply_defaults_adds_missing_keywords_and_locations(self):
        cfg = poller._apply_defaults(
            {"name": "Example", "ats": "greenhouse", "slug": "example"},
            {
                "keywords": ["software engineer"],
                "locations": ["United States", "Remote"],
                "max_age_days": 1,
            },
        )

        self.assertEqual(cfg["keywords"], ["software engineer"])
        self.assertEqual(cfg["locations"], ["United States", "Remote"])
        self.assertEqual(cfg["max_age_days"], 1)

    def test_company_can_override_keywords_and_locations(self):
        cfg = poller._apply_defaults(
            {
                "name": "Example",
                "keywords": ["data engineer"],
                "locations": [],
            },
            {
                "keywords": ["software engineer"],
                "locations": ["United States"],
            },
        )

        self.assertEqual(cfg["keywords"], ["data engineer"])
        self.assertEqual(cfg["locations"], [])

    def test_extra_keywords_and_locations_append_and_dedupe(self):
        cfg = poller._apply_defaults(
            {
                "name": "Example",
                "extra_keywords": ["software engineer", "cloud architect"],
                "extra_locations": ["Remote", "Canada"],
            },
            {
                "keywords": ["software engineer"],
                "locations": ["United States", "Remote"],
            },
        )

        self.assertEqual(cfg["keywords"], ["software engineer", "cloud architect"])
        self.assertEqual(cfg["locations"], ["United States", "Remote", "Canada"])

    def test_config_files_load_with_shared_defaults(self):
        companies = poller._load_config()
        missing = [
            company.get("name", "<unnamed>")
            for company in companies
            if not company.get("keywords") or not company.get("locations")
        ]

        self.assertGreater(len(companies), 0)
        self.assertEqual(missing, [])


class TestSuccessFactorsRouting(unittest.TestCase):

    def test_real_wipro_config_inherits_defaults_and_routes_ten_day_window(self):
        cfg = next(company for company in poller._load_config() if company["name"] == "Wipro")
        self.assertTrue(cfg["active"])
        self.assertEqual(cfg["max_age_days"], 10)
        self.assertIn("software engineer", cfg["keywords"])
        self.assertIn("ai developer", cfg["keywords"])
        self.assertEqual(cfg["locations"], ["United States", "Remote"])
        self.assertEqual(poller._get_scraper("successfactors").__name__, "scrapers.successfactors")
        scraper = MagicMock()
        scraper.scrape.return_value = []
        with patch.object(poller, "_get_scraper", return_value=scraper), \
                patch.object(poller, "store") as store, patch.object(poller, "notifier") as notifier:
            store.filter_new.return_value = []
            poller._poll_company(cfg)
            scraper.scrape.assert_called_once_with(
                keywords=cfg["keywords"], locations=cfg["locations"],
                max_age_days=10, company_name="Wipro", base_url="https://careers.wipro.com",
                locale="en_US", search_locations=["United States", ""],
                max_pages=200, max_runtime_seconds=120.0,
            )
            notifier.send_email.assert_not_called()
            store.mark_seen.assert_not_called()

    def test_missing_base_url_is_logged_without_scraping(self):
        scraper = MagicMock()
        with patch.object(poller, "_get_scraper", return_value=scraper), \
                patch.object(poller, "store") as store:
            poller._poll_company({"name": "Wipro", "ats": "successfactors"})
            scraper.scrape.assert_not_called()
            store.log_poll.assert_called_once_with("Wipro", "successfactors", 0, 0,
                                                   error="Missing base_url in config")


if __name__ == "__main__":
    unittest.main()
