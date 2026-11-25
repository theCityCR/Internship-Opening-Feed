"""Second-run report: which openings are new, closed or changed since the last snapshot.

Safety rule: an opening is only reported "closed" when its source was fetched *completely* in
this run. If a source failed or came back partial, its old openings are carried over untouched
instead of being declared closed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Job, SourceResult

# Fields whose change counts as "changed". Description edits are caught through description_hash.
WATCHED = ["title", "location", "date_posted", "apply_url", "description_hash"]


def load_snapshot(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text()) if p.is_file() else {}


def compute_diff(old: dict[str, Any], jobs: list[Job], results: list[SourceResult]) -> dict[str, Any]:
    complete = {r.name for r in results if r.complete}
    current = {j.key: j.to_record() for j in jobs}
    old_jobs: dict[str, dict] = old.get("jobs", {})

    new = [k for k in current if k not in old_jobs]
    closed, carried = [], []
    for k, rec in old_jobs.items():
        if k in current:
            continue
        if rec["source"] in complete:
            closed.append(k)
        else:
            carried.append(k)
    changed: dict[str, dict[str, list]] = {}
    for k, rec in current.items():
        if k in old_jobs:
            delta = {f: [old_jobs[k].get(f), rec.get(f)] for f in WATCHED
                     if old_jobs[k].get(f) != rec.get(f)}
            if delta:
                changed[k] = delta
    return {"first_run": not old_jobs, "new": new, "closed": closed, "changed": changed,
            "carried_over_incomplete_source": carried,
            "closed_records": {k: old_jobs[k] for k in closed}}


def build_snapshot(old: dict[str, Any], jobs: list[Job], diff: dict[str, Any], when: str) -> dict[str, Any]:
    """Current openings, plus openings of incomplete sources carried over (not closed)."""
    keep = {j.key: j.to_record() for j in jobs}
    for k in diff["carried_over_incomplete_source"]:
        keep[k] = old["jobs"][k]
    return {"generated_at": when, "jobs": keep}


def save_snapshot(path: str | Path, snap: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=1))
