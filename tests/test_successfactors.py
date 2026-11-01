"""Offline SuccessFactors tests. No production DB, SMTP, or network access."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests

from scrapers import Job
from scrapers import successfactors as sf


NOW = datetime(2026, 11, 1, 16, 30, tzinfo=timezone.utc)
BASE_URL = "https://careers.wipro.com"


def item(job_id="160017", title="Junior Forward Deployed Engineer", date="10/26/26",
         offices=None, countries=None, **extra):
    return {"response": {
        "id": job_id,
        "unifiedStandardTitle": title,
        "unifiedUrlTitle": title.replace(" ", "-"),
        "unifiedStandardStart": date,
        "jobLocationShort": offices if offices is not None else [
            "Plano, USA-TX, USA, 75024<br/>", "Boston, USA-MA, USA, 2108<br/>",
        ],
        "jobLocationCountry": countries if countries is not None else ["United States"],
        **extra,
    }}


def response(rows, total=None):
    result = MagicMock()
    result.json.return_value = {
        "totalJobs": len(rows) if total is None else total,
        "jobSearchResult": rows,
    }
    return result


class TestParsing(unittest.TestCase):
    def test_dates_are_timezone_aware_and_support_source_formats(self):
        for text in ("10/26/26", "10/26/2026", "2026-10-26"):
            with self.subTest(text=text):
                self.assertEqual(sf._parse_date(text), datetime(2026, 10, 26, tzinfo=timezone.utc))

    def test_bad_dates_return_none(self):
        for text in (None, "", "bad", "2/30/26", {}, 123):
            self.assertIsNone(sf._parse_date(text))

    def test_parses_multiple_locations_and_posted_date(self):
        parsed = sf._parse_search_item(item(), BASE_URL, "en_US")
        self.assertEqual(parsed["posted_text"], "2026-10-26")
        self.assertIn("Plano", parsed["location"])
        self.assertIn("Boston", parsed["location"])
        self.assertIn("United States", parsed["location"])
        self.assertNotIn("<br", parsed["location"])
        self.assertEqual(parsed["link"], BASE_URL + "/job/Junior-Forward-Deployed-Engineer/160017-en_US")

    def test_location_fallback_preserves_cities_states_and_country(self):
        row = item(offices=[], countries=["United States"],
                   sfstd_jobLocation_obj=["Plano", "Boston"], jobLocationState=["Texas", "Massachusetts"])
        parsed = sf._parse_search_item(row, BASE_URL, "en_US")
        self.assertEqual(parsed["location"], "Plano; Boston; Texas; Massachusetts; United States")

    def test_encodes_slug_without_double_encoding(self):
        row = item(unifiedUrlTitle="AI-Developer-%28Entry-Level%29")
        self.assertIn("AI-Developer-%28Entry-Level%29/", sf._parse_search_item(row, BASE_URL, "en_US")["link"])

    def test_bad_rows_are_skipped(self):
        for row in (None, [], "oops", {}, {"response": []}, item(job_id=""), item(title=""),
                    item(unifiedUrlTitle="", urlTitle="")):
            self.assertIsNone(sf._parse_search_item(row, BASE_URL, "en_US"))


class TestSearchPage(unittest.TestCase):
    def test_requests_date_order_with_no_search_keyword_bias(self):
        session = MagicMock()
        session.post.return_value = response([item()], total=37)
        rows, total = sf._search_page(session, BASE_URL, "en_US", "United States", 2, 7)
        self.assertEqual(total, 37)
        self.assertEqual(len(rows), 1)
        session.post.assert_called_once_with(
            BASE_URL + "/services/recruiting/v1/jobs",
            json={"keywords": "", "locale": "en_US", "location": "United States",
                  "pageNumber": 2, "sortBy": "date"}, timeout=7,
        )

    def test_empty_response_without_job_list_is_valid(self):
        session = MagicMock()
        session.post.return_value.json.return_value = {"totalJobs": 0}
        self.assertEqual(sf._search_page(session, BASE_URL, "en_US", "", 0, 20), ([], 0))

    def test_rejects_malformed_response_instead_of_treating_it_as_no_jobs(self):
        session = MagicMock()
        for payload in ([], {}, {"totalJobs": -1}, {"totalJobs": True}, {"totalJobs": 2},
                        {"totalJobs": 2, "jobSearchResult": {}},
                        {"totalJobs": 0, "jobSearchResult": [item()]}):
            with self.subTest(payload=payload):
                session.post.return_value.json.return_value = payload
                with self.assertRaises(ValueError):
                    sf._search_page(session, BASE_URL, "en_US", "", 0, 20)


class TestScrape(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        session_patch = patch.object(sf, "_make_session", return_value=self.session)
        now_patch = patch.object(sf, "_now", return_value=NOW)
        sleep_patch = patch.object(sf.time, "sleep")
        for patcher in (session_patch, now_patch, sleep_patch):
            patcher.start()
            self.addCleanup(patcher.stop)

    def scrape(self, **kwargs):
        return sf.scrape(**{
            "base_url": BASE_URL, "company_name": "Wipro",
            "keywords": ["forward deployed engineer", "software engineer", "ai developer"],
            "locations": ["United States", "Remote"], "max_age_days": 10,
            "search_locations": ["United States"], **kwargs,
        })

    def test_returns_job_objects_and_closes_session(self):
        self.session.post.return_value = response([item()])
        jobs = self.scrape()
        self.assertEqual(len(jobs), 1)
        self.assertIsInstance(jobs[0], Job)
        self.assertEqual(jobs[0].company, "Wipro")
        self.assertEqual(jobs[0].posted_text, "2026-10-26")
        self.session.__exit__.assert_called_once()
        self.session.get.assert_not_called()  # No per-JD enrichment.

    def test_ten_day_window_includes_whole_boundary_date(self):
        self.session.post.return_value = response([
            item("1", date="11/1/26"), item("2", date="10/22/26"), item("3", date="10/21/26"),
        ])
        self.assertEqual([job.link.split("/")[-1] for job in self.scrape()], ["1-en_US", "2-en_US"])

    def test_one_day_window_still_excludes_six_day_old_example(self):
        self.session.post.return_value = response([item()])
        self.assertEqual(self.scrape(max_age_days=1), [])

    def test_ai_developer_matches_extra_keyword_but_old_example_is_excluded(self):
        self.session.post.return_value = response([
            item("1", title="AI Developer (Entry Level)", date="10/26/26"),
            item("2", title="AI Developer (Entry Level)", date="4/10/26"),
        ])
        self.assertEqual(len(self.scrape()), 1)

    def test_filters_seniority_keyword_foreign_onsite_future_expiry_and_unknown_date(self):
        self.session.post.return_value = response([
            item("1", title="Senior Software Engineer"),
            item("2", title="Accountant"),
            item("3", offices=["Bengaluru, India"], countries=["India"]),
            item("4", date="11/2/26"),
            item("5", unifiedStandardEnd="10/31/26"),
            item("6", date=None),
            item("7", unifiedStandardEnd="11/1/26"),
        ])
        with self.assertLogs(sf.logger, level="WARNING"):
            jobs = self.scrape()
        self.assertEqual(len(jobs), 1)
        self.assertTrue(jobs[0].link.endswith("7-en_US"))

    def test_global_remote_allowed_but_foreign_onsite_is_not(self):
        self.session.post.return_value = response([
            item("1", offices=["Remote - Canada"], countries=["Canada"]),
            item("2", offices=["Toronto, Canada"], countries=["Canada"]),
        ])
        self.assertEqual(len(self.scrape(search_locations=[""])), 1)

    def test_multi_country_job_with_us_office_is_allowed(self):
        self.session.post.return_value = response([
            item(offices=["Toronto, Canada", "Boston, MA"], countries=["Canada", "United States"]),
        ])
        self.assertEqual(len(self.scrape()), 1)

    def test_paginates_until_reported_total_not_assumed_page_size(self):
        self.session.post.side_effect = [
            response([item("1")], total=2), response([item("2")], total=2),
        ]
        self.assertEqual(len(self.scrape()), 2)
        self.assertEqual([call.kwargs["json"]["pageNumber"] for call in self.session.post.call_args_list], [0, 1])

    def test_stops_after_whole_sorted_page_older_than_cutoff(self):
        self.session.post.side_effect = [
            response([item("1")], total=20), response([item("2", date="10/21/26")], total=20),
        ]
        self.assertEqual(len(self.scrape()), 1)
        self.assertEqual(self.session.post.call_count, 2)

    def test_unsorted_page_disables_early_stop_and_finds_later_recent_job(self):
        self.session.post.side_effect = [
            response([item("1", date="10/22/26"), item("2", date="10/26/26")], total=4),
            response([item("3", date="10/20/26")], total=4),
            response([item("4", date="10/25/26")], total=4),
        ]
        with self.assertLogs(sf.logger, level="WARNING") as logs:
            jobs = self.scrape()
        self.assertEqual(len(jobs), 3)
        self.assertEqual(self.session.post.call_count, 3)
        self.assertIn("out of order", " ".join(logs.output))

    def test_missing_date_disables_early_stop(self):
        self.session.post.side_effect = [
            response([item("1", date=None), item("2", date="10/20/26")], total=3),
            response([item("3")], total=3),
        ]
        with self.assertLogs(sf.logger, level="WARNING"):
            self.assertEqual(len(self.scrape()), 1)

    def test_repeated_page_stops_with_warning(self):
        self.session.post.return_value = response([item()], total=20)
        with self.assertLogs(sf.logger, level="WARNING") as logs:
            self.assertEqual(len(self.scrape()), 1)
        self.assertEqual(self.session.post.call_count, 2)
        self.assertIn("repeated", " ".join(logs.output))

    def test_global_query_dedup_does_not_stop_at_overlap_with_us(self):
        self.session.post.side_effect = [
            response([item()], total=1),
            response([item()], total=2),
            response([item("2", offices=["Remote - UK"], countries=["United Kingdom"])], total=2),
        ]
        self.assertEqual(len(self.scrape(search_locations=["United States", ""])), 2)
        self.assertEqual(self.session.post.call_count, 3)

    def test_page_cap_is_observable(self):
        self.session.post.return_value = response([item()], total=20)
        with self.assertLogs(sf.logger, level="WARNING") as logs:
            self.assertEqual(len(self.scrape(max_pages=1)), 1)
        self.assertIn("max_pages=1", " ".join(logs.output))

    def test_runtime_limit_stops_before_network_request(self):
        with patch.object(sf.time, "monotonic", side_effect=[0, 121, 121]):
            with self.assertLogs(sf.logger, level="WARNING") as logs:
                self.assertEqual(self.scrape(max_runtime_seconds=120), [])
        self.session.post.assert_not_called()
        self.assertIn("runtime limit", " ".join(logs.output))

    def test_request_timeout_is_bounded_by_remaining_runtime(self):
        self.session.post.return_value = response([item()])
        self.assertEqual(len(self.scrape(max_runtime_seconds=2)), 1)
        timeout = self.session.post.call_args.kwargs["timeout"]
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 2)

    def test_http_error_is_logged_and_never_raises_or_retries(self):
        self.session.post.return_value.raise_for_status.side_effect = requests.HTTPError("403 forbidden")
        with self.assertLogs(sf.logger, level="ERROR"):
            self.assertEqual(self.scrape(), [])
        self.assertEqual(self.session.post.call_count, 1)

    def test_bad_json_is_logged_and_never_raises(self):
        self.session.post.return_value.json.side_effect = ValueError("invalid JSON")
        with self.assertLogs(sf.logger, level="ERROR"):
            self.assertEqual(self.scrape(), [])

    def test_request_failure_preserves_previous_matches_and_closes_session(self):
        self.session.post.side_effect = [response([item()], total=20), requests.Timeout("timeout")]
        with self.assertLogs(sf.logger, level="ERROR"):
            self.assertEqual(len(self.scrape()), 1)
        self.session.__exit__.assert_called_once()

    def test_early_empty_page_warns_instead_of_claiming_full_coverage(self):
        self.session.post.return_value = response([], total=20)
        with self.assertLogs(sf.logger, level="WARNING") as logs:
            self.assertEqual(self.scrape(), [])
        self.assertIn("empty", " ".join(logs.output))

    def test_default_scopes_are_us_then_worldwide(self):
        self.session.post.return_value = response([])
        self.scrape(search_locations=None)
        self.assertEqual([c.kwargs["json"]["location"] for c in self.session.post.call_args_list],
                         ["United States", ""])

    def test_empty_scopes_still_make_worldwide_request(self):
        self.session.post.return_value = response([])
        self.scrape(search_locations=[])
        self.session.post.assert_called_once()
        self.assertEqual(self.session.post.call_args.kwargs["json"]["location"], "")

    def test_invalid_config_does_not_make_requests(self):
        for config in ({"base_url": ""}, {"base_url": "wipro.com"}, {"max_pages": 0},
                       {"max_runtime_seconds": 0}):
            with self.assertLogs(sf.logger, level="ERROR"):
                self.assertEqual(self.scrape(**config), [])
        self.session.post.assert_not_called()
