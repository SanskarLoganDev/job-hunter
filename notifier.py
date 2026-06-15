"""
notifier.py

Builds and sends the alert email.

Kept deliberately isolated from the scrapers and store so it can be
tested independently (render_email has no side effects; send_email
is the only function that touches the network).

Gmail app-password setup (one-time):
  1. Google account → Security → 2-Step Verification → ON
  2. Search "App passwords" → create one for "Mail / Windows Computer"
  3. Copy the 16-char password into .env as SMTP_PASS
"""

import os
import smtplib
import ssl
import logging
from email.message import EmailMessage
from typing import List

from scrapers import Job

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email rendering  (pure function — no side effects, easy to test)
# ---------------------------------------------------------------------------

def render_email(company: str, jobs: List[Job]) -> tuple[str, str]:
    """
    Return (subject, html_body) for a batch of new jobs at one company.
    Never raises.
    """
    subject = f"[JobHunter] {len(jobs)} new role{'s' if len(jobs) != 1 else ''} at {company}"

    rows = "\n".join(
        f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #e8eaed;">
            <a href="{j.link}" style="color:#1a73e8;text-decoration:none;font-weight:500;">
              {j.title}
            </a>
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #e8eaed;color:#5f6368;">
            {j.location or "—"}
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #e8eaed;color:#5f6368;">
            {j.posted_text or "—"}
          </td>
        </tr>"""
        for j in jobs
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:Roboto,Arial,sans-serif;background:#f8f9fa;">
  <table width="100%" cellpadding="0" cellspacing="0"
         style="max-width:700px;margin:24px auto;background:#fff;
                border:1px solid #dadce0;border-radius:12px;overflow:hidden;">

    <tr>
      <td style="background:#1a73e8;padding:20px 24px;">
        <span style="color:#fff;font-size:20px;font-weight:700;">JobHunter</span>
        <span style="color:#bdd5ff;font-size:14px;margin-left:12px;">New roles alert</span>
      </td>
    </tr>

    <tr>
      <td style="padding:20px 24px 8px;">
        <p style="margin:0;font-size:15px;color:#202124;">
          Found <strong>{len(jobs)}</strong> new
          role{'s' if len(jobs) != 1 else ''} at <strong>{company}</strong>:
        </p>
      </td>
    </tr>

    <tr>
      <td style="padding:0 24px 20px;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border:1px solid #e8eaed;border-radius:8px;overflow:hidden;margin-top:12px;">
          <tr style="background:#f8f9fa;">
            <th style="padding:10px 12px;text-align:left;font-size:13px;
                       color:#5f6368;font-weight:500;border-bottom:1px solid #e8eaed;">
              Role
            </th>
            <th style="padding:10px 12px;text-align:left;font-size:13px;
                       color:#5f6368;font-weight:500;border-bottom:1px solid #e8eaed;">
              Location
            </th>
            <th style="padding:10px 12px;text-align:left;font-size:13px;
                       color:#5f6368;font-weight:500;border-bottom:1px solid #e8eaed;">
              Posted
            </th>
          </tr>
          {rows}
        </table>
      </td>
    </tr>

    <tr>
      <td style="padding:12px 24px 24px;border-top:1px solid #e8eaed;">
        <p style="margin:0;font-size:12px;color:#80868b;">
          Sent by JobHunter poller &mdash; apply fast, first 48 hours matter most.
        </p>
      </td>
    </tr>

  </table>
</body>
</html>"""

    return subject, html


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def send_email(subject: str, html: str) -> None:
    """
    Send an HTML email using SMTP credentials from .env.

    Raises RuntimeError with a human-readable message on failure so
    poller.py can log it without crashing the whole run.
    """
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    recipient = os.getenv("RECIPIENT_EMAIL")

    if not smtp_user or not smtp_pass:
        raise RuntimeError(
            "Missing SMTP_USER or SMTP_PASS in .env — "
            "set up a Gmail App Password (16 chars, no spaces)."
        )
    if not recipient:
        raise RuntimeError("Missing RECIPIENT_EMAIL in .env.")

    msg = EmailMessage()
    msg["From"]    = smtp_user
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.set_content("Your email client does not support HTML.")
    msg.add_alternative(html, subtype="html")

    ctx = ssl.create_default_context()
    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as s:
                s.login(smtp_user, smtp_pass.replace(" ", ""))
                s.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(smtp_user, smtp_pass.replace(" ", ""))
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(
            "Gmail auth failed. Make sure 2-Step Verification is ON and you're "
            "using a 16-char App Password (not your normal password)."
        ) from e
    except smtplib.SMTPException as e:
        raise RuntimeError(f"SMTP error: {type(e).__name__}: {e}") from e

    logger.info("Email sent → %s | %s", recipient, subject)
