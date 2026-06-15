"""
scrapers/__init__.py

Defines the single Job dataclass that every scraper must return.
poller.py and store.py only ever deal with this shape — scrapers
are completely interchangeable as long as they return List[Job].
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
    posted_text: str = ""           # human-readable date string e.g. "2025-06-01"
    posted_dt: Optional[object] = None  # datetime or None

    # Internal dedup key — set automatically, do not set manually
    uid: str = field(init=False)

    def __post_init__(self):
        # uid is a stable fingerprint: same job on two runs == same uid
        # We normalise the link (strip trailing slash + query params that
        # are session tokens) so the same posting doesn't look new each run.
        from urllib.parse import urlparse, urlunparse
        p = urlparse(self.link.strip().rstrip("/"))
        clean = urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
        self.uid = clean or self.link
