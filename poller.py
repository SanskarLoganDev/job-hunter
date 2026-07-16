"""
poller.py

Entry point called by Windows Task Scheduler every 30 minutes.

Flow:
  1. Acquire a lock file — exit immediately if another instance is running.
  2. Load all config-*.yaml files from the config/ folder alphabetically.
  3. For each active company across all configs:
       a. Route to the right scraper module.
       b. Diff results against seen_jobs in the DB.
       c. If new jobs found: send email, then mark them as seen.
       d. Log the outcome to poll_log + log file.
  4. Release lock file.

One company failing never affects the others.

CONFIG FOLDER: config/
  config-amazon.yaml          — Amazon
  config-ashby.yaml           — Ashby companies
  config-greenhouse.yaml      — Greenhouse companies
  config-lever.yaml           — Lever companies
  config-smartrecruiters.yaml — SmartRecruiters companies
  config-*.yaml                — any future ATS config, auto-discovered at startup

Windows notes:
  - Uses msvcrt.locking() for the lock file (fcntl is Unix-only).
  - Path separator handled by pathlib throughout.
"""

import importlib
import logging
import logging.handlers
import msvcrt
import os
import random
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

import store
import notifier

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR   = Path(__file__).parent
LOG_FILE   = BASE_DIR / "logs" / "poller.log"
LOCK_FILE  = BASE_DIR / "logs" / "poller.lock"
CONFIG_DIR = BASE_DIR / "config"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=7, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    root.addHandler(fh)
    root.addHandler(ch)


logger = logging.getLogger("poller")

# ---------------------------------------------------------------------------
# Lock file (Windows-compatible via msvcrt)
# ---------------------------------------------------------------------------

_lock_fh = None


def _acquire_lock() -> bool:
    global _lock_fh
    LOCK_FILE.parent.mkdir(exist_ok=True)
    try:
        _lock_fh = open(LOCK_FILE, "w")
        msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
        return True
    except OSError:
        if _lock_fh:
            _lock_fh.close()
            _lock_fh = None
        return False


def _release_lock() -> None:
    global _lock_fh
    if _lock_fh:
        try:
            _lock_fh.seek(0)
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
            _lock_fh.close()
        except Exception:
            pass
        finally:
            _lock_fh = None


# ---------------------------------------------------------------------------
# Config loader — loads ALL config-*.yaml files from config/ folder
# ---------------------------------------------------------------------------

def _load_config() -> list:
    """
    Load and merge companies from all config-*.yaml files in config/.
    Files loaded alphabetically — all treated equally, no required primary.
    Aborts only if the config/ folder itself is missing or empty.
    """
    if not CONFIG_DIR.exists():
        logger.critical("config/ folder not found at %s — aborting.", CONFIG_DIR)
        sys.exit(1)

    all_paths = sorted(CONFIG_DIR.glob("config-*.yaml"))

    if not all_paths:
        logger.critical("No config-*.yaml files found in %s — aborting.", CONFIG_DIR)
        sys.exit(1)

    all_companies = []

    for path in all_paths:
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            logger.error("%s is malformed: %s — skipping.", path.name, e)
            continue
        except OSError as e:
            logger.error("Cannot read %s: %s — skipping.", path.name, e)
            continue

        companies = data.get("companies", [])
        logger.debug("Loaded %d company config(s) from %s", len(companies), path.name)
        all_companies.extend(companies)

    if not all_companies:
        logger.warning("No companies found across all config files — nothing to poll.")

    return all_companies


# ---------------------------------------------------------------------------
# Scraper router
# ---------------------------------------------------------------------------

_SCRAPER_MAP = {
    "amazon":          "scrapers.amazon",
    "deltek":          "scrapers.deltek",
    "microsoft":       "scrapers.microsoft",
    "greenhouse":      "scrapers.greenhouse",
    "ashby":           "scrapers.ashby",
    "lever":           "scrapers.lever",
    "smartrecruiters": "scrapers.smartrecruiters",
    # "workday":    "scrapers.workday",   # not yet built
}

# ATS platforms that use a slug for the per-company API call
_SLUG_BASED = {"greenhouse", "lever", "ashby", "smartrecruiters"}


def _get_scraper(ats: str):
    module_path = _SCRAPER_MAP.get(ats.lower())
    if not module_path:
        logger.error("Unknown ATS '%s' — no scraper available.", ats)
        return None
    try:
        return importlib.import_module(module_path)
    except ImportError as e:
        logger.error("Could not import scraper '%s': %s", module_path, e)
        return None


# ---------------------------------------------------------------------------
# Single-company poll
# ---------------------------------------------------------------------------

def _poll_company(cfg: dict) -> None:
    name      = cfg.get("name", "Unknown")
    ats       = cfg.get("ats", "")
    keywords  = cfg.get("keywords", [])
    locations = cfg.get("locations", [])
    max_age   = int(cfg.get("max_age_days", 2))
    limit     = int(cfg.get("detail_fetch_limit", 30))
    active    = cfg.get("active", True)

    if not active:
        logger.info("Skipping %s (active: false)", name)
        return

    logger.info("── Polling %s  [%s] ──", name, ats)

    scraper = _get_scraper(ats)
    if scraper is None:
        store.log_poll(name, ats, 0, 0, error=f"No scraper for ATS '{ats}'")
        return

    scrape_kwargs = dict(
        keywords=keywords,
        locations=locations,
        max_age_days=max_age,
        company_name=name,
    )

    # Amazon, SmartRecruiters, and Workday use detail_fetch_limit —
    # Amazon for date enrichment, SmartRecruiters for fetching the real
    # postingUrl (its list endpoint only returns an API `ref` URL).
    # Deltek does NOT use detail_fetch_limit — url field is in the list response.
    if ats in ("amazon", "smartrecruiters", "workday"):
        scrape_kwargs["detail_fetch_limit"] = limit

    # Slug-based scrapers (greenhouse, lever, ashby, workable, smartrecruiters)
    # need the slug (for smartrecruiters this is the companyIdentifier).
    if ats in _SLUG_BASED:
        slug = cfg.get("slug", "")
        if not slug:
            logger.error("%s: 'slug' required for %s scraper", name, ats)
            store.log_poll(name, ats, 0, 0, error="Missing slug in config")
            return
        scrape_kwargs["slug"] = slug

    error_msg = None
    jobs      = []
    new_jobs  = []

    try:
        jobs = scraper.scrape(**scrape_kwargs)
        logger.info("%s: scraped %d job(s) after all filters", name, len(jobs))

        new_jobs = store.filter_new(jobs)
        logger.info("%s: %d new (unseen) job(s)", name, len(new_jobs))

        if new_jobs:
            subject, html = notifier.render_email(name, new_jobs)
            notifier.send_email(subject, html)
            store.mark_seen(new_jobs)
            logger.info("%s: email sent + %d job(s) marked seen", name, len(new_jobs))
        else:
            logger.info("%s: nothing new to report", name)

    except Exception as e:
        error_msg = str(e)
        logger.error("%s: unexpected error — %s", name, e, exc_info=True)

    store.log_poll(
        company=name,
        scraper=ats,
        found=len(jobs),
        new_jobs=len(new_jobs),
        error=error_msg,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _setup_logging()
    load_dotenv(BASE_DIR / ".env")

    logger.info("=" * 60)
    logger.info("JobHunter poller starting  (pid %s)", os.getpid())

    if not _acquire_lock():
        logger.warning("Another poller instance is already running — exiting.")
        sys.exit(0)

    try:
        store.init_db()
        companies = _load_config()
        logger.info("Loaded %d total company config(s)", len(companies))

        for cfg in companies:
            try:
                _poll_company(cfg)
            except Exception as e:
                logger.error(
                    "Unhandled error for '%s': %s",
                    cfg.get("name", "?"), e, exc_info=True,
                )
            time.sleep(random.uniform(0.5, 1.0))

        logger.info(
            "JobHunter poller finished. Total seen jobs in DB: %d",
            store.get_seen_count(),
        )

    finally:
        _release_lock()
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
