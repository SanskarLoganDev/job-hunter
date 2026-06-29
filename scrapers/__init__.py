"""
scrapers/__init__.py

Defines the single Job dataclass that every scraper must return,
plus shared filtering utilities used across all scrapers.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    # Required — every scraper must populate these
    title: str
    company: str
    link: str

    # Optional — populate when available
    location: str = ""
    posted_text: str = ""
    posted_dt: Optional[object] = None

    # Internal dedup key — set automatically, do not set manually
    uid: str = field(init=False)

    def __post_init__(self):
        from urllib.parse import urlparse, urlunparse
        p = urlparse(self.link.strip().rstrip("/"))
        clean = urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
        self.uid = clean or self.link


# ---------------------------------------------------------------------------
# Seniority exclusion list
#
# Titles containing any of these terms (case-insensitive, whole-word) are
# filtered out across ALL scrapers via is_junior_enough().
#
# TO ADD/REMOVE A TERM: edit this list — no other code changes needed.
# ---------------------------------------------------------------------------
_SENIOR_TERMS = [
    "senior",
    "sr.",
    " sr ",          # "Sr Software Engineer"
    "staff",
    "principal",
    "lead",
    "director",
    "head of",
    "vp ",
    "vice president",
    "manager",
    "distinguished",
    "fellow",
]


def is_junior_enough(title: str) -> bool:
    """
    Return True if the job title does NOT contain a seniority term.
    Return False (exclude the job) if it does.

    Uses simple substring matching — fast and sufficient for job titles.
    Case-insensitive.

    Examples:
      "Software Engineer"              → True  (keep)
      "Senior Software Engineer"       → False (exclude)
      "Staff Engineer"                 → False (exclude)
      "Software Engineer, Safeguards"  → True  (keep)
      "Sr. Software Engineer"          → False (exclude)
      "Engineering Manager"            → False (exclude)
    """
    title_lower = title.lower()
    return not any(term.lower() in title_lower for term in _SENIOR_TERMS)
