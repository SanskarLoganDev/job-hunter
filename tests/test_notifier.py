"""
tests/test_notifier.py

Tests for notifier.py — email rendering + send path.

Run with:  python -m pytest tests/test_notifier.py -v
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from scrapers import Job
from notifier import render_email, send_email


def _make_job(n: int, days_old: int = 0) -> Job:
    return Job(
        title=f"Software Engineer {n}",
        company="Amazon",
        link=f"https://www.amazon.jobs/en/jobs/{n}/swe",
        location="Seattle, WA",
        posted_text=(datetime.now(timezone.utc) - timedelta(days=days_old)).strftime("%Y-%m-%d"),
        posted_dt=datetime.now(timezone.utc) - timedelta(days=days_old),
    )


def _make_job_no_date(n: int) -> Job:
    return Job(
        title=f"Software Engineer {n}",
        company="Amazon",
        link=f"https://www.amazon.jobs/en/jobs/{n}/swe",
        location="Remote",
        posted_text="",
        posted_dt=None,
    )


class TestRenderEmail(unittest.TestCase):

    def test_subject_contains_company(self):
        subject, _ = render_email("Amazon", [_make_job(1)])
        self.assertIn("Amazon", subject)

    def test_subject_contains_count(self):
        subject, _ = render_email("Amazon", [_make_job(1), _make_job(2)])
        self.assertIn("2", subject)

    def test_singular_role_grammar(self):
        subject, _ = render_email("Amazon", [_make_job(1)])
        self.assertIn("1 new role", subject)

    def test_plural_roles_grammar(self):
        subject, _ = render_email("Amazon", [_make_job(1), _make_job(2)])
        self.assertIn("2 new roles", subject)

    def test_html_contains_job_title(self):
        _, html = render_email("Amazon", [_make_job(42)])
        self.assertIn("Software Engineer 42", html)

    def test_html_contains_link(self):
        _, html = render_email("Amazon", [_make_job(1)])
        self.assertIn("https://www.amazon.jobs/en/jobs/1/swe", html)

    def test_html_contains_location(self):
        _, html = render_email("Amazon", [_make_job(1)])
        self.assertIn("Seattle, WA", html)

    def test_html_is_valid_structure(self):
        _, html = render_email("Amazon", [_make_job(1)])
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("</html>", html)

    def test_multiple_jobs_all_appear(self):
        jobs = [_make_job(i) for i in range(5)]
        _, html = render_email("Amazon", jobs)
        for i in range(5):
            self.assertIn(f"Software Engineer {i}", html)

    def test_missing_location_shows_dash(self):
        job = Job(title="SWE", company="Amazon",
                  link="https://www.amazon.jobs/en/jobs/1/swe",
                  location="")
        _, html = render_email("Amazon", [job])
        self.assertIn("—", html)

    # ── Sorting tests ─────────────────────────────────────────────────────

    def test_jobs_sorted_newest_first(self):
        """Newest job must appear before older job in the rendered HTML."""
        old_job  = _make_job(1, days_old=5)   # older
        new_job  = _make_job(2, days_old=0)   # newer
        # Pass old first deliberately to confirm sorting overrides input order
        _, html = render_email("Amazon", [old_job, new_job])
        pos_new = html.index(f"Software Engineer 2")
        pos_old = html.index(f"Software Engineer 1")
        self.assertLess(pos_new, pos_old,
                        "Newer job should appear before older job in HTML")

    def test_jobs_with_no_date_go_to_bottom(self):
        """Jobs with no posted_dt must appear after dated jobs."""
        dated_job   = _make_job(1, days_old=0)
        no_date_job = _make_job_no_date(2)
        _, html = render_email("Amazon", [no_date_job, dated_job])
        pos_dated   = html.index("Software Engineer 1")
        pos_no_date = html.index("Software Engineer 2")
        self.assertLess(pos_dated, pos_no_date,
                        "Job with date should appear before job without date")

    def test_sort_does_not_change_count(self):
        jobs = [_make_job(i, days_old=i) for i in range(5)]
        _, html = render_email("Amazon", jobs)
        for i in range(5):
            self.assertIn(f"Software Engineer {i}", html)


class TestSendEmail(unittest.TestCase):

    _ENV = {
        "SMTP_USER": "sender@gmail.com",
        "SMTP_PASS": "abcdabcdabcdabcd",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "RECIPIENT_EMAIL": "recipient@gmail.com",
    }

    @patch("notifier.smtplib.SMTP")
    @patch.dict("os.environ", _ENV)
    def test_send_calls_smtp(self, MockSMTP):
        instance = MockSMTP.return_value.__enter__.return_value
        send_email("Test Subject", "<html>test</html>")
        self.assertTrue(instance.send_message.called)

    @patch.dict("os.environ", {**_ENV, "SMTP_USER": ""})
    def test_missing_smtp_user_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            send_email("subject", "<html></html>")
        self.assertIn("SMTP_USER", str(ctx.exception))

    @patch.dict("os.environ", {**_ENV, "RECIPIENT_EMAIL": ""})
    def test_missing_recipient_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            send_email("subject", "<html></html>")
        self.assertIn("RECIPIENT_EMAIL", str(ctx.exception))

    @patch("notifier.smtplib.SMTP")
    @patch.dict("os.environ", _ENV)
    def test_auth_failure_raises_runtime_error(self, MockSMTP):
        import smtplib
        instance = MockSMTP.return_value.__enter__.return_value
        instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
        with self.assertRaises(RuntimeError) as ctx:
            send_email("subject", "<html></html>")
        self.assertIn("auth failed", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
