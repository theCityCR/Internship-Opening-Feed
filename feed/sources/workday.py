"""Workday (CXS JSON endpoints behind a company's careers site). Not a Greenhouse/Lever board.

Listing:  POST {host}/wday/cxs/{tenant}/{site}/jobs   (max 20 per page; `total` on page 1)
Detail:   GET  {host}/wday/cxs/{tenant}/{site}{externalPath}
Both are the same unauthenticated calls the public careers page makes. Nothing is submitted
(the POST only carries search filters).

Scope: the board's own "Job Type = Intern" facet, so internships whose title lacks the word
"intern" are still found, optionally limited to one country to stay inside the request budget.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..classify import internship_rule
from ..client import FetchError, StringClient
from ..models import Job, SourceResult
from ..text import html_to_text
from .base import Source

PAGE = 20


class WorkdaySource(Source):
    def __init__(self, name: str, company: str, host: str, tenant: str, site: str, apply_base: str,
                 country_facet: tuple[str, str] | None = None, intern_label: str = "Intern"):
        self.name, self.company = name, company
        self.host, self.tenant, self.site, self.apply_base = host, tenant, site, apply_base
        self.country_facet = country_facet
        self.intern_label = intern_label

    @property
    def _base(self) -> str:
        return f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}"

    def applied_facets(self, first_page: dict) -> dict[str, list[str]]:
        """Turn facet *labels* into the facet *ids* Workday wants. Location facets are nested."""
        facets = first_page.get("facets", [])
        intern_ids: list[str] = []
        for group in facets:
            if group.get("facetParameter") == "workerSubType":
                intern_ids = [v["id"] for v in group.get("values", [])
                              if self.intern_label.lower() in v.get("descriptor", "").lower()]
        if not intern_ids:
            raise FetchError(f"{self.name}: no '{self.intern_label}' job-type facet found")
        applied = {"workerSubType": intern_ids}
        if self.country_facet:
            param, label = self.country_facet
            ids: list[str] = []
            for group in facets:
                for sub in group.get("values", []):
                    if sub.get("facetParameter") == param:
                        ids = [v["id"] for v in sub.get("values", []) if v.get("descriptor") == label]
            if not ids:
                raise FetchError(f"{self.name}: location facet {label!r} not found")
            applied[param] = ids
        return applied

    def list_all(self, client: StringClient, applied: dict) -> tuple[list[dict], int]:
        """Read every page until offset reaches the site's own `total`."""
        url = f"{self._base}/jobs"
        postings: list[dict] = []
        total, offset = 0, 0
        while True:
            page = client.fetch(url, "POST", {"appliedFacets": applied, "limit": PAGE,
                                              "offset": offset, "searchText": ""})
            if offset == 0:
                total = page.get("total", 0)
            batch = page.get("jobPostings", [])
            postings.extend(batch)
            offset += PAGE
            if not batch or offset >= total:
                break
        return postings, total

    def parse_detail(self, listing: dict, detail: dict) -> Job:
        info = detail.get("jobPostingInfo") or {}
        desc = html_to_text(info.get("jobDescription"))
        title = info.get("title") or listing.get("title", "")
        # The Job Type facet is itself a structured intern signal; title/description may add detail.
        rule = internship_rule(title, desc, structured=True)
        job_id = info.get("jobReqId") or (listing.get("bulletFields") or [""])[0]
        # primary location first, then the posting's additional locations (listing says "2 Locations")
        locs = [info.get("location") or listing.get("locationsText", "")]
        locs += [x for x in info.get("additionalLocations") or [] if x not in locs]
        return Job(
            source=self.name, company=self.company, job_id=job_id, title=title,
            location="; ".join(x for x in locs if x),
            date_posted=info.get("startDate"),
            apply_url=info.get("externalUrl") or f"{self.apply_base}{listing['externalPath']}",
            description=desc, structured_intern=True, internship_rule=rule,
        )

    def fetch(self, client: StringClient) -> SourceResult:
        before = client.requests_made
        scope = f"job type {self.intern_label}"
        if self.country_facet:
            scope += f", {self.country_facet[1]} only"
        res = SourceResult(self.name, self.company, scope=scope)

        # One tiny request just to discover the facet ids for the labels above.
        probe = client.fetch(f"{self._base}/jobs", "POST",
                             {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
        postings, total = self.list_all(client, self.applied_facets(probe))
        res.site_total, res.fetched_total = total, len(postings)

        def one(p: dict):
            try:
                return p, client.fetch(f"{self._base}{p['externalPath']}")
            except FetchError as e:
                res.notes.append(f"detail failed for {p.get('externalPath')}: {e}")
                return p, None

        with ThreadPoolExecutor(max_workers=6) as ex:
            for p, detail in ex.map(one, postings):
                if detail is None:
                    continue
                job = self.parse_detail(p, detail)
                label = job.internship_rule or "structured"
                res.rule_counts[label] = res.rule_counts.get(label, 0) + 1
                res.jobs.append(job)
        # postings lost to a failed detail fetch make the run incomplete
        res.complete = len(postings) == total and len(res.jobs) == len(postings)
        res.string_requests = client.requests_made - before
        return res

