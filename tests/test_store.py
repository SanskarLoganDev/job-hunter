"""
tests/test_store.py

Tests for store.py — the seen_jobs diff + DB layer.

Run with:  python -m pytest tests/test_store.py -v
"""

import unittest
from unittest.mock import patch

from scrapers import Job
import store

_COMPANY_DOMAINS = {
    "Amazon":  "https://www.amazon.jobs/en/jobs",
    "Carvana": "https://boards.greenhouse.io/carvana/jobs",
}


def _make_job(uid_suffix: str, company: str = "Amazon") -> Job:
    base = _COMPANY_DOMAINS.get(company, f"https://careers.{company.lower()}.com/jobs")
    return Job(
        title=f"Software Engineer {uid_suffix}",
        company=company,
        link=f"{base}/{uid_suffix}/swe",
        location="Remote",
        posted_text="2026-06-15",
    )


class TestStore(unittest.TestCase):

    def setUp(self):
        import sqlite3
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._connect_patcher = patch("store._connect", return_value=self._conn)
        self._connect_patcher.start()
        self._conn.executescript(store._DDL)

    def tearDown(self):
        self._connect_patcher.stop()
        self._conn.close()

    def test_all_new_when_db_empty(self):
        jobs = [_make_job("1"), _make_job("2")]
        self.assertEqual(len(store.filter_new(jobs)), 2)

    def test_already_seen_filtered_out(self):
        job = _make_job("1")
        store.mark_seen([job])
        self.assertEqual(store.filter_new([job]), [])

    def test_mix_of_new_and_seen(self):
        seen_job = _make_job("seen")
        new_job  = _make_job("new")
        store.mark_seen([seen_job])
        result = store.filter_new([seen_job, new_job])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].uid, new_job.uid)

    def test_empty_input_returns_empty(self):
        self.assertEqual(store.filter_new([]), [])

    def test_mark_seen_persists(self):
        job = _make_job("100")
        store.mark_seen([job])
        self.assertEqual(store.filter_new([job]), [])

    def test_mark_seen_idempotent(self):
        job = _make_job("200")
        store.mark_seen([job])
        store.mark_seen([job])
        self.assertEqual(store.filter_new([job]), [])

    def test_mark_seen_multiple_companies(self):
        amazon_job  = _make_job("1", company="Amazon")
        carvana_job = _make_job("1", company="Carvana")
        self.assertNotEqual(amazon_job.uid, carvana_job.uid,
            "Test setup error: both jobs have the same uid")
        store.mark_seen([amazon_job])
        result = store.filter_new([carvana_job])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].uid, carvana_job.uid)

    def test_log_poll_writes_row(self):
        store.log_poll("Amazon", "amazon", found=10, new_jobs=2)
        logs = store.get_recent_poll_logs(limit=5)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["company"], "Amazon")
        self.assertEqual(logs[0]["found"], 10)
        self.assertEqual(logs[0]["new_jobs"], 2)
        self.assertIsNone(logs[0]["error"])

    def test_log_poll_records_error(self):
        store.log_poll("Amazon", "amazon", found=0, new_jobs=0, error="timeout")
        self.assertEqual(store.get_recent_poll_logs()[0]["error"], "timeout")

    def test_seen_count_increments(self):
        self.assertEqual(store.get_seen_count(), 0)
        store.mark_seen([_make_job("a"), _make_job("b")])
        self.assertEqual(store.get_seen_count(), 2)


if __name__ == "__main__":
    unittest.main()
