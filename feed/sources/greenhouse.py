"""Greenhouse public board API: one request returns every posting with its description."""
from __future__ import annotations

from ..classify import internship_rule
from ..client import StringClient
from ..models import Job, SourceResult
from ..text import html_to_text
from .base import Source, iso_date


class GreenhouseSource(Source):
    def __init__(self, name: str, company: str, board: str):
        self.name, self.company, self.board = name, company, board

    def parse(self, data: dict) -> SourceResult:
        jobs_raw = data.get("jobs", [])
        total = (data.get("meta") or {}).get("total")
        res = SourceResult(self.name, self.company, scope="all open postings (board API)",
                           site_total=total, fetched_total=len(jobs_raw))
        for j in jobs_raw:
            desc = html_to_text(j.get("content"), unescape_first=True)
            rule = internship_rule(j.get("title", ""), desc, structured=False)
            if not rule:
                continue
            res.rule_counts[rule] = res.rule_counts.get(rule, 0) + 1
            res.jobs.append(Job(
                source=self.name, company=j.get("company_name") or self.company,
                job_id=str(j["id"]), title=j["title"],
                location=(j.get("location") or {}).get("name") or "",
                date_posted=iso_date(j.get("first_published")),
                apply_url=j["absolute_url"], description=desc, internship_rule=rule,
            ))
        res.complete = total is None or total == len(jobs_raw)
        return res

    def fetch(self, client: StringClient) -> SourceResult:
        before = client.requests_made
        url = f"https://boards-api.greenhouse.io/v1/boards/{self.board}/jobs?content=true"
        res = self.parse(client.fetch(url))
        res.string_requests = client.requests_made - before
        return res
