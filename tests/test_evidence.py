"""Quoted-evidence checking, whole-number money matching and the regex-only grad_years."""
from feed.extract import _money_seen, apply_evidence, find_grad_years

TEXT = ("Software Engineer Intern - Summer 2027\n"
        "Our internship hourly rates are standard. The expected hourly rate is 38 USD – 94 USD.\n"
        "Must be graduating in 2027 or 2028. This is a hybrid role.")


def ans(**kw):
    base = {"category": "backend", "term": None, "season": None, "pay_min": None, "pay_max": None,
            "pay_currency": None, "pay_period": None, "work_mode": None, "visa_sponsorship": None,
            "evidence": {"term": None, "season": None, "pay": None, "work_mode": None, "visa_sponsorship": None}}
    ev = kw.pop("evidence", {})
    base.update(kw)
    base["evidence"].update(ev)
    return base


def test_value_with_a_real_quote_is_kept():
    a = ans(term="Summer 2027", season="Summer", pay_min=38, pay_max=94, pay_currency="USD", pay_period="hour",
            work_mode="hybrid",
            evidence={"term": "Software Engineer Intern - Summer 2027", "season": "Summer 2027",
                      "pay": "The expected hourly rate is 38 USD – 94 USD.", "work_mode": "This is a hybrid role."})
    out = apply_evidence(a, TEXT)
    assert (out["term"], out["season"], out["pay_min"], out["pay_max"], out["work_mode"]) == \
        ("Summer 2027", "Summer", 38, 94, "hybrid")


def test_value_without_a_quote_is_dropped():
    out = apply_evidence(ans(work_mode="onsite", term="Summer 2027", season="Summer"), TEXT)
    assert out["work_mode"] is None and out["term"] is None and out["season"] is None


def test_invented_quote_is_dropped():
    a = ans(work_mode="onsite", evidence={"work_mode": "This role is fully onsite in Santa Clara."})
    assert apply_evidence(a, TEXT)["work_mode"] is None


def test_quote_that_does_not_contain_the_value_is_dropped():
    # real sentence, but it does not state a season, so the model's "Summer" is rejected
    a = ans(season="Summer", evidence={"season": "Must be graduating in 2027 or 2028."})
    assert apply_evidence(a, TEXT)["season"] is None
    # real sentence, wrong pay figure
    a = ans(pay_min=20, pay_max=94, evidence={"pay": "The expected hourly rate is 38 USD – 94 USD."})
    assert apply_evidence(a, TEXT)["pay_min"] is None


def test_quote_matching_ignores_case_whitespace_and_curly_quotes():
    text = "We don’t sponsor visas.\nThis   is a Hybrid role."
    a = ans(work_mode="hybrid", visa_sponsorship="no",
            evidence={"work_mode": "this is a hybrid role.", "visa_sponsorship": "We don't sponsor visas."})
    out = apply_evidence(a, text)
    assert out["work_mode"] == "hybrid" and out["visa_sponsorship"] == "no"


def test_model_grad_years_is_ignored_and_regex_supplies_it():
    a = ans()
    a["grad_years"] = "Pursuing a PhD"
    assert "grad_years" not in apply_evidence(a, TEXT)
    assert find_grad_years(TEXT) == "graduating in 2027 or 2028"
    assert find_grad_years("Must be planning on graduating in 2028. This should be your final internship.") \
        == "graduating in 2028"
    assert find_grad_years("Class of 2027 only") == "Class of 2027"


def test_grad_years_regex_needs_a_year():
    assert find_grad_years("anticipated graduation date (month and year) must be indicated") is None
    assert find_grad_years("Pursuing a PhD. Graduating soon.") is None


def test_money_match_is_whole_number():
    assert _money_seen(20, "20 USD - 94 USD")
    assert not _money_seen(20, "Summer 2027 internship")       # 20 is inside 2027
    assert not _money_seen(20, "pay up to 10,200 per year")
    assert _money_seen(10500, "$10,500/month") and _money_seen(45.5, "$45.50 per hour")
    assert _money_seen(90000, "$90k")
