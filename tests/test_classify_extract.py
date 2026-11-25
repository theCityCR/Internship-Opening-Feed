from feed.classify import heuristic_category, internship_rule
from feed.extract import regex_extract, validate


def test_title_rule_whole_words_only():
    assert internship_rule("Software Engineer, Intern", "", False) == "title"
    assert internship_rule("2027 Internships: Deep Learning", "", False) == "title"
    assert internship_rule("Engineering Co-op", "", False) == "title"
    assert internship_rule("Internal Tools Engineer", "", False) is None
    assert internship_rule("International Tax Director", "", False) is None


def test_structured_and_description_rules():
    assert internship_rule("Year at Acme - Engineer", "", True) == "structured"
    assert internship_rule("Student Developer", "Join us for this 12-week summer internship.", False) == "description"
    # a passing mention of internships is not enough
    assert internship_rule("Engineer", "Internship experience is a plus.", False) is None


def test_regex_pay_variants():
    assert regex_extract("The expected hourly rate is 38 USD – 94 USD.")["pay_min"] == 38
    r = regex_extract("Pay: $5,900 - $10,500 per month. Fall 2027.")
    assert (r["pay_min"], r["pay_max"], r["pay_period"], r["term"]) == (5900, 10500, "month", "Fall 2027")
    assert regex_extract("We pay $45-$60/hour")["pay_period"] == "hour"


def test_regex_single_figure_pay():
    r = regex_extract("The estimated salary range for this position is estimated to be $10,500/month.")
    assert (r["pay_min"], r["pay_max"], r["pay_period"], r["pay_currency"]) == (10500, 10500, "month", "USD")


def test_graduation_date_is_not_the_internship_term():
    t = "Expected to graduate in spring/summer 2028. Join our Summer 2027 program."
    assert regex_extract(t)["term"] == "Summer 2027"
    assert "term" not in regex_extract("with the expectation of graduating in spring/summer 2028")


def test_company_boilerplate_is_not_work_mode():
    assert "work_mode" not in regex_extract("Many teams do offer hybrid options (WFH a day or two a week).")


def test_regex_leaves_empty_when_text_is_silent():
    assert regex_extract("A great team building internal tools in an international company.") == {}


def test_work_mode():
    assert regex_extract("This is a hybrid role")["work_mode"] == "hybrid"
    assert regex_extract("fully remote")["work_mode"] == "remote"


def test_validate_drops_ungrounded_model_output():
    text = "Summer 2027 internship. Pay is $40-$50 per hour."
    ok = validate({"category": "backend", "season": "Summer", "term": "Summer 2027",
                   "pay_min": 40, "pay_max": 50, "pay_currency": "USD", "pay_period": "hour"}, text)
    assert ok["pay_min"] == 40 and ok["season"] == "Summer"
    bad = validate({"category": "wizardry", "season": "Winter", "term": "Winter 2030",
                    "pay_min": 99, "pay_max": 120, "pay_currency": "USD", "pay_period": "hour",
                    "visa_sponsorship": "yes"}, text)
    assert bad["category"] == "other"                 # not an allowed category
    assert "season" not in bad and "term" not in bad  # not in the text
    assert "pay_min" not in bad                       # invented figures dropped
    assert "visa_sponsorship" not in bad              # text never mentions visas


def test_validate_rejects_degree_level_as_grad_years():
    text = "Must be pursuing a B.S., M.S., or Ph.D. degree. Summer 2027."
    assert "grad_years" not in validate({"category": "other", "grad_years": "B.S., M.S., or Ph.D. degree"}, text)
    ok = validate({"category": "other", "grad_years": "graduating in 2027 or 2028"}, "Must be graduating in 2027 or 2028.")
    assert ok["grad_years"] == "graduating in 2027 or 2028"


def test_grad_years_needs_a_real_year():
    t = "Anticipated graduation date (month and year) must be clearly indicated on your resume. Pursuing a PhD."
    for bad in ("anticipated graduation date (month and year)", "within 12-months of graduation", "Pursuing a PhD"):
        assert "grad_years" not in validate({"category": "other", "grad_years": bad}, t)
    assert validate({"category": "other", "grad_years": "graduating in 2028"}, "Must be graduating in 2028.")["grad_years"]
    # a year that is not in the text is rejected
    assert "grad_years" not in validate({"category": "other", "grad_years": "graduating in 2031"}, "Must be graduating in 2028.")


def test_validate_drops_season_converted_from_months():
    text = "Paid full-time internship between May-August, 2027."
    out = validate({"category": "other", "term": "May-August, 2027", "season": "Summer"}, text)
    assert "season" not in out          # the word "summer" never appears
    assert out["term"] == "2027"        # date range reduced to the year


def test_validate_keeps_year_when_model_invented_the_season_word():
    text = "Paid full-time internship between May-August, 2027."
    out = validate({"category": "other", "term": "Summer 2027", "season": "Summer"}, text)
    assert "season" not in out and out["term"] == "2027"
    # an invented year is still dropped entirely
    assert "term" not in validate({"category": "other", "term": "Summer 2025", "season": "Summer"}, "Summer internship.")


def test_validate_combines_season_and_year_when_text_has_both():
    text = "PCIe Design Verification Intern - Spring 2027. February 2027 - August 2027."
    out = validate({"category": "hardware", "term": "February 2027 - August 2027", "season": "Spring"}, text)
    assert (out["season"], out["term"]) == ("Spring", "Spring 2027")


def test_validate_drops_visa_answer_when_no_visa_words_in_text():
    out = validate({"category": "other", "visa_sponsorship": "no"}, "U.S. Person Required. Report scams to the FBI.")
    assert "visa_sponsorship" not in out


def test_validate_drops_work_mode_without_a_supporting_word():
    assert "work_mode" not in validate({"category": "other", "work_mode": "onsite"}, "Build GPUs. Summer 2027.")


def test_validate_keeps_pay_past_old_7000_char_cut():
    from feed.extract import MAX_DESC_CHARS
    assert MAX_DESC_CHARS > 13500       # longest real posting is 13.4k chars


def test_record_validation_counts_altered_answers():
    from feed.extract import LLMExtractor
    llm = LLMExtractor("unused", cache_dir="/tmp/_llm_test_cache")
    raw = {"category": "other", "work_mode": "onsite", "term": "2027 Internships"}
    llm.record_validation(raw, validate(raw, "Summer"))
    assert llm.answers_altered == 1 and llm.altered["work_mode"] == 1 and llm.altered["term"] == 1


def test_heuristic_category():
    assert heuristic_category("Machine Learning Engineer, Intern") == "ML/AI"
    assert heuristic_category("Quantitative Trader Intern") == "quant"
    assert heuristic_category("Product Design Intern") == "other"
