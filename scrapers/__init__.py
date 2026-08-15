"""
scrapers/__init__.py

Defines the single Job dataclass that every scraper must return,
plus shared filtering utilities used across all scrapers.
"""

from dataclasses import dataclass, field
import re
from typing import List, Optional


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


# ---------------------------------------------------------------------------
# Shared location filtering
#
# Config intent:
#   locations: [United States, Remote]
# means:
#   - keep any explicitly remote job, including international remote jobs
#   - keep any US office job, even when the ATS only says "City, ST"
#
# We intentionally do NOT maintain city lists. The stable signal is the state
# abbreviation/name, plus explicit country strings when the ATS provides them.
# ---------------------------------------------------------------------------

_US_TERMS = {
    "us",
    "u.s.",
    "u.s",
    "usa",
    "u.s.a.",
    "united states",
    "united states of america",
}

_REMOTE_TERMS = {"remote"}

_US_STATE_ABBR = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

_US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
}

_FOREIGN_COUNTRY_TERMS = {
    "argentina", "australia", "austria", "belgium", "brazil", "canada",
    "chile", "china", "colombia", "denmark",
    "europe", "finland", "france", "germany", "hong kong", "india",
    "indonesia", "ireland", "italy", "japan", "malaysia",
    "netherlands", "new zealand", "norway", "philippines",
    "poland", "portugal", "romania", "serbia", "singapore", "spain",
    "sweden", "switzerland", "taiwan", "thailand", "uae", "uk",
    "united arab emirates", "united kingdom", "vietnam",
}

_US_STATE_ABBR_RE = re.compile(
    r"(?:^|[,\-/|;•(])\s*("
    + "|".join(sorted(_US_STATE_ABBR))
    + r")\s*(?:$|[,\-/|;•)])",
    re.IGNORECASE,
)


def _normalise_terms(terms: List[str]) -> set:
    return {term.strip().lower() for term in terms if term and term.strip()}


def _has_word(text: str, term: str) -> bool:
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
        text,
        re.IGNORECASE,
    ) is not None


def _allows_remote(allowed_terms: set) -> bool:
    return bool(allowed_terms & _REMOTE_TERMS)


def _allows_us(allowed_terms: set) -> bool:
    return bool(allowed_terms & _US_TERMS)


def _is_remote_location(location_lower: str) -> bool:
    return _has_word(location_lower, "remote")


def _looks_like_us_location(location: str) -> bool:
    """
    Return True when a location string appears to be in the US.

    Fast path examples:
      "United States", "USA", "Austin, TX, US"

    City/state examples:
      "San Francisco, CA", "New York, NY", "Boston, Massachusetts"

    Explicit foreign country terms override state-name guesses so
    "Brussels, Belgium" never sneaks in via the "US" substring.
    """
    loc_lower = location.lower()

    has_explicit_us = any(_has_word(loc_lower, term) for term in _US_TERMS)
    has_explicit_foreign = any(
        _has_word(loc_lower, term) for term in _FOREIGN_COUNTRY_TERMS
    )

    if has_explicit_us:
        return True
    if has_explicit_foreign:
        return False

    if _US_STATE_ABBR_RE.search(location):
        return True

    return any(_has_word(loc_lower, state) for state in _US_STATE_NAMES)


def is_location_allowed(location: str, allowed: List[str]) -> bool:
    """
    Return True if a job location matches the config's allowed locations.

    Rules:
      - Empty allowed list means no location filter.
      - If config allows Remote, any location containing "Remote" passes,
        including international remote jobs.
      - If config allows US/USA/United States, US city/state strings pass even
        when the ATS omits the country.
      - Other allowed terms keep the old substring behavior for company-
        specific city filters like "San Francisco" or "New York".
    """
    allowed_terms = _normalise_terms(allowed)
    if not allowed_terms:
        return True

    location = (location or "").strip()
    loc_lower = location.lower()

    if _allows_remote(allowed_terms) and _is_remote_location(loc_lower):
        return True

    for term in allowed_terms:
        if term in _US_TERMS or term in _REMOTE_TERMS:
            continue
        if term in loc_lower:
            return True

    if _allows_us(allowed_terms) and _looks_like_us_location(location):
        return True

    return False
