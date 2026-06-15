"""
tests/test_notifier.py

Tests for notifier.py — email rendering + send path.

render_email() is a pure function and tested directly.
send_email() is tested with SMTP mocked so no real email is sent.

Run with:  python -m pytest tests/test_notifier.py -v
"""

import unittest
from unittest.mock import patch, MagicMock

from scrapers import Job
from notifier import render_email, send_email


def _make_job(n: int) -> Job:
    return Job(
        title=f"Software Engineer {n}",
        company="Amazon",
        link=f"https://www.amazon.jobs/en/jobs/{n}/swe",
        location="Seattle, WA",
        posted_text="2025-06-01",
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
