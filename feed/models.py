"""The normalised job record shared by every source."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any

CATEGORIES = ["backend", "frontend", "full-stack", "mobile", "ML/AI", "data",
              "infrastructure", "security", "quant", "hardware", "other"]
SEASONS = ["Summer", "Fall", "Winter", "Spring"]
WORK_MODES = ["onsite", "hybrid", "remote"]


@dataclass
class Job:
    # --- from the source -------------------------------------------------
    source: str                 # adapter name, e.g. "stripe"
    company: str
    job_id: str                 # the source's own ID (Greenhouse id, Lever uuid, Workday JR number)
    title: str
    location: str
    date_posted: str | None     # ISO date, YYYY-MM-DD
    apply_url: str
    description: str = ""       # plain text; kept in memory/cache, not written to the feed
    structured_intern: bool = False   # the source's own structured field says "intern"
    source_work_mode: str | None = None  # work mode stated by the source's own field (Lever workplaceType)
    internship_rule: str | None = None  # "title" | "structured" | "description"
    # --- filled by extract.py ---------------------------------------------
    category: str = "other"
    term: str | None = None             # e.g. "Summer 2027"
    season: str | None = None           # Summer | Fall | Winter | Spring
    pay_min: float | None = None
    pay_max: float | None = None
    pay_currency: str | None = None
    pay_period: str | None = None       # hour | week | month | year
    work_mode: str | None = None        # onsite | hybrid | remote
    visa_sponsorship: str | None = None  # yes | no
    grad_years: str | None = None       # free text, e.g. "Class of 2027 or 2028"

    @property
    def key(self) -> str:
        return f"{self.source}:{self.job_id}"

    @property
    def description_hash(self) -> str:
        return hashlib.sha256(" ".join(self.description.split()).encode()).hexdigest()[:16]

    def to_record(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("description")
        d.pop("structured_intern")
        d.pop("source_work_mode")
        d["description_hash"] = self.description_hash
        return d


@dataclass
class SourceResult:
    name: str
    company: str
    scope: str                          # human-readable description of what was requested
    jobs: list[Job] = field(default_factory=list)
    site_total: int | None = None       # the total the source itself reports for `scope`
    fetched_total: int = 0              # postings actually read within `scope` (before intern filter)
    complete: bool = False              # every page read and fetched_total == site_total (when known)
    rule_counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    string_requests: int = 0
