"""Parsers run against saved real responses (tests/fixtures); no network."""
import json
from pathlib import Path

import pytest

from feed.client import FetchError
from feed.sources.greenhouse import GreenhouseSource
from feed.sources.lever import LeverSource
from feed.sources.workday import WorkdaySource

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text())


def test_greenhouse_keeps_only_internships_and_checks_total():
    res = GreenhouseSource("stripe", "Stripe", "stripe").parse(load("greenhouse_stripe.json"))
    assert res.complete and res.site_total == res.fetched_total == 5
    assert len(res.jobs) == 3                       # 3 intern-titled, 2 other postings dropped
    j = res.jobs[0]
    assert j.job_id.isdigit() and j.apply_url.startswith("http")
    assert j.date_posted and len(j.date_posted) == 10
    assert j.internship_rule == "title"
    assert "&lt;" not in j.description              # Greenhouse double-escaped HTML was decoded


def test_greenhouse_incomplete_when_total_mismatch():
    data = load("greenhouse_stripe.json")
    data["meta"]["total"] = 99
    assert GreenhouseSource("stripe", "Stripe", "stripe").parse(data).complete is False


def test_lever_normalises_and_uses_structured_commitment():
    res = LeverSource("palantir", "Palantir", "palantir").parse(load("lever_palantir.json"))
    assert len(res.jobs) == 3
    for j in res.jobs:
        assert j.job_id and j.apply_url.startswith("https://jobs.lever.co/")
        assert j.date_posted and j.location


def test_lever_workplace_type_becomes_source_work_mode():
    data = load("lever_palantir.json")
    res = LeverSource("palantir", "Palantir", "palantir").parse(data)
    assert all(j.source_work_mode in ("onsite", "hybrid", "remote") for j in res.jobs)
    data[0]["workplaceType"] = "unspecified"
    assert LeverSource("p", "P", "p").parse(data).jobs[0].source_work_mode is None


def test_source_work_mode_wins_over_text():
    from feed.extract import enrich
    from feed.models import Job
    j = Job(source="s", company="c", job_id="1", title="Intern", location="x", date_posted=None,
            apply_url="u", description="This is a remote role.", source_work_mode="hybrid")
    enrich(j, None)
    assert j.work_mode == "hybrid"
    assert "source_work_mode" not in j.to_record()


def test_workday_additional_locations_are_kept():
    detail = {"jobPostingInfo": {"title": "Intern", "jobReqId": "JR1", "jobDescription": "<p>x</p>",
                                 "location": "US, CA, Santa Clara",
                                 "additionalLocations": ["US, TX, Austin", "US, CA, Santa Clara"],
                                 "externalUrl": "https://x/y"}}
    j = WorkdaySource("n", "N", "h", "t", "s", "https://x").parse_detail({"externalPath": "/p", "locationsText": "3 Locations"}, detail)
    assert j.location == "US, CA, Santa Clara; US, TX, Austin"      # primary first, no duplicate


def test_workday_facet_ids_resolved_from_labels():
    src = WorkdaySource("nvidia", "NVIDIA", "h", "t", "s", "https://x", country_facet=("locationHierarchy1", "United States"))
    applied = src.applied_facets(load("workday_list.json"))
    assert applied["workerSubType"] == ["0c40f6bd1d8f10adf6dae42e46d44a17"]   # "Intern (Fixed Term)"
    assert applied["locationHierarchy1"] == ["2fcb99c455831013ea52fb338f2932d8"]


def test_workday_unknown_country_fails_loudly():
    src = WorkdaySource("nvidia", "NVIDIA", "h", "t", "s", "https://x", country_facet=("locationHierarchy1", "Atlantis"))
    with pytest.raises(FetchError):
        src.applied_facets(load("workday_list.json"))


def test_workday_detail_parse():
    detail = load("workday_detail.json")
    listing = {"title": "t", "externalPath": "/job/x_JR1", "locationsText": "US", "bulletFields": ["JR1"]}
    j = WorkdaySource("nvidia", "NVIDIA", "h", "t", "s", "https://x").parse_detail(listing, detail)
    assert j.job_id == detail["jobPostingInfo"]["jobReqId"]
    assert j.apply_url == detail["jobPostingInfo"]["externalUrl"]
    assert j.structured_intern and j.internship_rule
    assert "<p>" not in j.description
