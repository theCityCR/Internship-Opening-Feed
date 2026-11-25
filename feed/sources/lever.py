"""Lever public postings API: one request returns every posting with its description."""
from __future__ import annotations

from ..classify import internship_rule
from ..client import StringClient
from ..models import Job, SourceResult
from .base import Source, epoch_ms_to_date


def _lever_text(j: dict) -> str:
    parts = [j.get("descriptionPlain") or ""]
    for lst in j.get("lists") or []:
        parts.append(f"{lst.get('text', '')}\n{_strip_tags(lst.get('content', ''))}")
    parts.append(j.get("additionalPlain") or "")
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _strip_tags(s: str) -> str:
    from ..text import html_to_text
    return html_to_text(s)


class LeverSource(Source):
    def __init__(self, name: str, company: str, slug: str):
        self.name, self.company, self.slug = name, company, slug

    def parse(self, data: list) -> SourceResult:
        res = SourceResult(self.name, self.company, scope="all open postings (postings API)",
                           site_total=len(data), fetched_total=len(data), complete=True)
        res.notes.append("Lever returns the full list in one response and states no separate total, "
                         "so completeness is by construction (no pagination), not cross-checked.")
        for j in data:
            cats = j.get("categories") or {}
            desc = _lever_text(j)
            structured = (cats.get("commitment") or "").lower() in ("internship", "intern")
            rule = internship_rule(j.get("text", ""), desc, structured)
            if not rule:
                continue
            res.rule_counts[rule] = res.rule_counts.get(rule, 0) + 1
            locs = cats.get("allLocations") or ([cats["location"]] if cats.get("location") else [])
            res.jobs.append(Job(
                source=self.name, company=self.company, job_id=j["id"], title=j["text"],
                location="; ".join(locs), date_posted=epoch_ms_to_date(j.get("createdAt")),
                apply_url=j.get("hostedUrl") or j.get("applyUrl") or "",
                description=desc, structured_intern=structured, internship_rule=rule,
            ))
        return res

    def fetch(self, client: StringClient) -> SourceResult:
        before = client.requests_made
        res = self.parse(client.fetch(f"https://api.lever.co/v0/postings/{self.slug}?mode=json"))
        res.string_requests = client.requests_made - before
        return res
