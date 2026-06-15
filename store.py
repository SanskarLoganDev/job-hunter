"""
store.py

SQLite persistence layer.

Two tables:
  - seen_jobs : every job uid we have ever notified about.
  - poll_log  : one row per poll run — timestamp, company, counts, error.
"""

import sqlite3
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from scrapers import Job

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent / "jobs.db"

_DDL = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    uid          TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    company      TEXT NOT NULL,
    link         TEXT NOT NULL,
    location     TEXT,
    posted_text  TEXT,
    first_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poll_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at       TEXT NOT NULL,
    company      TEXT NOT NULL,
    scraper      TEXT NOT NULL,
    found        INTEGER NOT NULL DEFAULT 0,
    new_jobs     INTEGER NOT NULL DEFAULT 0,
    error        TEXT
);
"""


def _now_iso() -> str:
    """Return the current UTC time as an ISO string. Single source of truth."""
    return datetime.now(timezone.utc).isoformat()


def _connect(retries: int = 3, backoff: float = 1.0) -> sqlite3.Connection:
    last_err = None
    for attempt in range(retries):
        try:
            conn = sqlite3.connect(str(_DB_PATH), timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError as e:
            last_err = e
            if attempt < retries - 1:
                sleep = backoff * (2 ** attempt)
                logger.warning("DB locked, retrying in %.1fs (attempt %d/%d)",
                               sleep, attempt + 1, retries)
                time.sleep(sleep)
    raise last_err


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_DDL)
    logger.debug("DB initialised at %s", _DB_PATH)


def filter_new(jobs: List[Job]) -> List[Job]:
    if not jobs:
        return []
    try:
        with _connect() as conn:
            placeholders = ",".join("?" * len(jobs))
            uids = [j.uid for j in jobs]
            rows = conn.execute(
                f"SELECT uid FROM seen_jobs WHERE uid IN ({placeholders})", uids
            ).fetchall()
            already_seen = {row["uid"] for row in rows}
            return [j for j in jobs if j.uid not in already_seen]
    except Exception as e:
        logger.error("filter_new failed: %s — treating all %d jobs as new", e, len(jobs))
        return jobs


def mark_seen(jobs: List[Job]) -> None:
    if not jobs:
        return
    now = _now_iso()
    rows = [
        (j.uid, j.title, j.company, j.link, j.location, j.posted_text, now)
        for j in jobs
    ]
    try:
        with _connect() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO seen_jobs
                   (uid, title, company, link, location, posted_text, first_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
    except Exception as e:
        logger.error("mark_seen failed: %s — %d jobs NOT recorded", e, len(jobs))


def log_poll(
    company: str,
    scraper: str,
    found: int,
    new_jobs: int,
    error: Optional[str] = None,
) -> None:
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO poll_log (ran_at, company, scraper, found, new_jobs, error)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (_now_iso(), company, scraper, found, new_jobs, error),
            )
    except Exception as e:
        logger.warning("log_poll failed (non-fatal): %s", e)


def get_seen_count() -> int:
    try:
        with _connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
    except Exception:
        return -1


def get_recent_poll_logs(limit: int = 20) -> list:
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM poll_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []
