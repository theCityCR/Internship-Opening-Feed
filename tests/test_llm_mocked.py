"""The Claude call itself, with a fake client: parsing, caching, budget cap and every failure fallback."""
import json
from types import SimpleNamespace

from feed.extract import LLMExtractor, enrich
from feed.models import Job

DESC = ("Our internship hourly rates are standard. The expected hourly rate is 38 USD – 94 USD.\n"
        "Must be graduating in 2027 or 2028. This is a hybrid role.")
TITLE = "Software Engineer Intern - Summer 2027"


def ans(**kw):
    base = {"category": "backend", "term": None, "season": None, "pay_min": None, "pay_max": None,
            "pay_currency": None, "pay_period": None, "work_mode": None, "visa_sponsorship": None,
            "evidence": {"term": None, "season": None, "pay": None, "work_mode": None, "visa_sponsorship": None}}
    ev = kw.pop("evidence", {})
    base.update(kw)
    base["evidence"].update(ev)
    return base


GOOD = json.dumps(ans(term="Summer 2027", season="Summer", work_mode="hybrid",
                      evidence={"term": TITLE, "season": "Summer 2027", "work_mode": "This is a hybrid role."}))


class FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def create(self, **kw):
        self.calls += 1
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=r)],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=100))


def llm_with(replies, tmp_path, max_usd=2.0):
    llm = LLMExtractor("unused", cache_dir=tmp_path, max_usd=max_usd)
    llm.client = SimpleNamespace(messages=FakeMessages(replies))
    return llm


def job():
    return Job(source="s", company="c", job_id="1", title=TITLE, location="x", date_posted=None,
               apply_url="u", description=DESC)


def test_end_to_end_with_fake_client(tmp_path):
    llm = llm_with([GOOD], tmp_path)
    j = job()
    assert enrich(j, llm) == "llm"
    assert (j.term, j.season, j.work_mode) == ("Summer 2027", "Summer", "hybrid")
    assert j.pay_min == 38 and j.pay_max == 94           # regex backs up pay
    assert j.grad_years == "graduating in 2027 or 2028"  # regex-only field
    assert llm.calls == 1 and llm.in_tokens == 1000 and llm.cost_usd > 0


def test_reply_with_prose_around_json_is_parsed(tmp_path):
    assert llm_with(["Here you go:\n" + GOOD + "\nHope that helps"], tmp_path).ask(job())["term"] == "Summer 2027"


def test_answer_is_cached(tmp_path):
    llm = llm_with([GOOD], tmp_path)
    llm.ask(job())
    llm.ask(job())
    assert llm.client.messages.calls == 1 and llm.cache_hits == 1


def test_garbage_reply_falls_back_to_regex(tmp_path):
    llm = llm_with(["I cannot do that"], tmp_path)
    j = job()
    assert enrich(j, llm) == "regex+fallback"
    assert llm.failures == 1 and j.pay_min == 38         # regex still filled pay


def test_api_error_falls_back_to_regex(tmp_path):
    llm = llm_with([RuntimeError("boom")], tmp_path)
    j = job()
    assert enrich(j, llm) == "regex+fallback"
    assert llm.failures == 1 and "boom" in llm.last_error


def test_budget_cap_stops_calls(tmp_path):
    llm = llm_with([GOOD, GOOD], tmp_path, max_usd=0.0001)
    llm.in_tokens = 10_000_000                           # already over the cap
    assert llm.ask(job()) is None and llm.budget_hit and llm.client.messages.calls == 0


def test_unquoted_model_answer_loses_its_values(tmp_path):
    j = job()
    enrich(j, llm_with([json.dumps(ans(work_mode="onsite", season="Winter"))], tmp_path))   # no evidence
    assert j.work_mode is None and j.season is None
