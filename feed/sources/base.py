from __future__ import annotations

from datetime import datetime, timezone

from ..client import StringClient
from ..models import SourceResult


class Source:
    name: str
    company: str

    def fetch(self, client: StringClient) -> SourceResult:  # pragma: no cover - interface
        raise NotImplementedError


def iso_date(value: str | None) -> str | None:
    """'2026-10-30T10:50:29-04:00' -> '2026-10-30' (the date as written by the source)."""
    return value[:10] if value and len(value) >= 10 else None


def epoch_ms_to_date(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
