"""
tests/test_poller.py

Tests for poller.py config default merging.

No scraper or network calls.
"""

import unittest

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


if __name__ == "__main__":
    unittest.main()
