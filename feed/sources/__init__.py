"""Source adapters. Each exposes `fetch(client) -> SourceResult`."""
from __future__ import annotations

from .base import Source
from .greenhouse import GreenhouseSource
from .lever import LeverSource
from .workday import WorkdaySource

# Every source is the company's own careers backend (or the board its careers page uses).
SOURCES: list[Source] = [
    GreenhouseSource(name="stripe", company="Stripe", board="stripe"),
    LeverSource(name="palantir", company="Palantir", slug="palantir"),
    WorkdaySource(
        name="nvidia", company="NVIDIA",
        host="nvidia.wd5.myworkdayjobs.com", tenant="nvidia", site="NVIDIAExternalCareerSite",
        apply_base="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        # Scope = "Intern (Fixed Term)" job type, United States only (keeps a run under budget).
        country_facet=("locationHierarchy1", "United States"),
    ),
]


def get_sources(names: list[str] | None = None) -> list[Source]:
    return [s for s in SOURCES if not names or s.name in names]
