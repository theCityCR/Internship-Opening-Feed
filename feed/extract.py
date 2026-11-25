"""Field extraction from a description: term/season, pay, work mode, visa, grad years, category.

Two layers:
  * regex_extract()  - offline, deterministic, conservative (used with --no-llm, and as the
                       check that model answers are grounded in the text).
  * LLMExtractor     - one Claude call per posting (cached by description hash), whose answer
                       is validated against the text: a pay figure or season that does not
                       literally appear in the description is discarded.
A field is left empty (None) whenever the text does not say.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any

from .classify import heuristic_category
from .models import CATEGORIES, Job

MODEL = "claude-haiku-4-5"
PRICE_IN_PER_MTOK = 1.00     # USD, claude-haiku-4-5 list price
PRICE_OUT_PER_MTOK = 5.00
MAX_DESC_CHARS = 16000   # longest posting seen is 13.4k chars; 7000 cut off a "$60 per hour" sentence
PROMPT_VERSION = "v6"   # bump to invalidate the LLM cache whenever SYSTEM changes

# ---------------------------------------------------------------- regex layer
_SEASON = r"(Summer|Fall|Autumn|Winter|Spring)"
TERM_RE = re.compile(rf"\b{_SEASON}\s+(20\d\d)\b", re.I)
_MONEY = r"(?:US\$|\$|USD\s?|£|€|CAD\s?|C\$)\s?(\d[\d,]*(?:\.\d+)?)\s*(k|K)?"
PAY_RE = re.compile(
    rf"{_MONEY}\s*(?:-|–|—|to|and)\s*(?:US\$|\$|USD\s?|£|€|CAD\s?|C\$)?\s?(\d[\d,]*(?:\.\d+)?)\s*(k|K)?"
    rf"(?:\s*(?:USD|CAD|GBP|EUR))?(?:\s*(?:/|per|an?)\s*(hour|hr|week|wk|month|mo|year|yr|annum))?", re.I)
_PERIOD_NORM = {"hour": "hour", "hr": "hour", "week": "week", "wk": "week", "month": "month",
                "mo": "month", "year": "year", "yr": "year", "annum": "year"}
_CURRENCY = {"$": "USD", "US$": "USD", "USD": "USD", "£": "GBP", "€": "EUR", "CAD": "CAD", "C$": "CAD"}


def _num(s: str, k: str | None) -> float:
    v = float(s.replace(",", ""))
    return v * 1000 if k else v


# "38 USD - 94 USD" (currency code AFTER the number, as NVIDIA writes it)
PAY_POST_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(USD|CAD|GBP|EUR)\s*(?:-|–|—|to)\s*(\d[\d,]*(?:\.\d+)?)\s*(USD|CAD|GBP|EUR)", re.I)
_PERIOD_WORDS = [("hourly", "hour"), ("per hour", "hour"), ("/hour", "hour"), ("monthly", "month"),
                 ("per month", "month"), ("weekly", "week"), ("per week", "week"),
                 ("annual", "year"), ("per year", "year"), ("yearly", "year")]


SINGLE_PAY_RE = re.compile(
    r"(US\$|\$|£|€|C\$)\s?(\d[\d,]*(?:\.\d+)?)\s*(k|K)?\s*(?:/|per\s+|a\s+)(hour|hr|week|wk|month|mo|year|yr)\b", re.I)


def _period_near(text: str, start: int) -> str | None:
    window = text[max(0, start - 120):start + 60].lower()
    best = None
    for word, per in _PERIOD_WORDS:
        i = window.rfind(word)
        if i != -1 and (best is None or i > best[0]):
            best = (i, per)
    return best[1] if best else None


def _find_pay(text: str) -> dict[str, Any]:
    m2 = PAY_POST_RE.search(text)
    if m2:
        lo_v, hi_v = _num(m2.group(1), None), _num(m2.group(3), None)
        if lo_v <= hi_v:
            return {"pay_min": lo_v, "pay_max": hi_v, "pay_currency": m2.group(2).upper(),
                    "pay_period": _period_near(text, m2.start())}
    for m in PAY_RE.finditer(text):
        lo, lok, hi, hik, per = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        lo_v, hi_v = _num(lo, lok), _num(hi, hik)
        if hi_v < lo_v or hi_v < 5:       # reject "$1-2" style noise
            continue
        sym = re.match(r"(US\$|\$|USD|£|€|CAD|C\$)", m.group(0), re.I)
        period = _PERIOD_NORM.get((per or "").lower())
        if not period:                    # infer from magnitude only when unambiguous
            period = "hour" if hi_v < 400 else ("year" if hi_v >= 20000 else None)
        return {"pay_min": lo_v, "pay_max": hi_v,
                "pay_currency": _CURRENCY.get(sym.group(1).upper() if sym else "$", "USD"),
                "pay_period": period}
    # single figure with an explicit period: "$10,000/month", "$45 per hour"
    m3 = SINGLE_PAY_RE.search(text)
    if m3:
        v = _num(m3.group(2), m3.group(3))
        return {"pay_min": v, "pay_max": v, "pay_currency": _CURRENCY.get(m3.group(1).upper(), "USD"),
                "pay_period": _PERIOD_NORM[m3.group(4).lower()]}
    return {}


# Company-wide boilerplate ("many teams offer hybrid options", "some roles allow remote work")
# says nothing about THIS role, so only role-specific phrasings count.
_HYBRID = re.compile(r"\bhybrid (?:role|position|internship|work (?:model|schedule|arrangement)|schedule|model)\b"
                     r"|\b(?:this|the) (?:role|position|internship) is (?:a )?hybrid\b"
                     r"|\bwork (?:in a )?hybrid\b|\bhybrid[:,]? \d days?\b", re.I)
_REMOTE = re.compile(r"\b(?:fully|100%|completely)\s+remote\b|\bremote[- ]first\b"
                     r"|\bthis (?:is a )?remote (?:role|position|internship)\b", re.I)
_ONSITE = re.compile(r"\bthis (?:is an? )?(?:on-?site|in[- ]office|in[- ]person) (?:role|position|internship)\b"
                     r"|\b(?:role|position|internship) is (?:an? )?(?:on-?site|in[- ]office|in[- ]person)\b"
                     r"|\bmust (?:work|be) (?:on-?site|in[- ]office|in the office)\b", re.I)
# Words a model-supplied work_mode must be grounded in (looser than the regexes above)
MODE_WORDS = {"hybrid": re.compile(r"\bhybrid\b", re.I),
              "remote": re.compile(r"\bremote\b", re.I),
              "onsite": re.compile(r"\bon-?site\b|\bin[- ]office\b|\bin[- ]person\b|\boffice\b", re.I)}


def _find_mode(text: str) -> str | None:
    if _HYBRID.search(text):
        return "hybrid"
    if _REMOTE.search(text):
        return "remote"
    if _ONSITE.search(text):
        return "onsite"
    return None


def regex_extract(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for m in TERM_RE.finditer(text):
        # "expected to graduate in spring/summer 2028" is a graduation date, not the internship term
        before = text[max(0, m.start() - 100):m.start()]
        before = re.split(r"[.!?\n]", before)[-1]          # same sentence only
        if re.search(r"graduat|class of|degree|completion", before, re.I):
            continue
        season = "Fall" if m.group(1).lower() == "autumn" else m.group(1).capitalize()
        out["season"], out["term"] = season, f"{season} {m.group(2)}"
        break
    out.update(_find_pay(text))
    mode = _find_mode(text)
    if mode:
        out["work_mode"] = mode
    return out


# ------------------------------------------------------------------ LLM layer
SYSTEM = """You extract structured facts from ONE internship job posting. Reply with a single JSON object and nothing else.
Rules:
- Only use what the text explicitly says. If the text does not say, use null. Never guess or infer.
- category: exactly one of backend, frontend, full-stack, mobile, ML/AI, data, infrastructure, security, quant, hardware, other. Judge by the work described (title first). Non-engineering roles (design, marketing, finance, sales) are "other". Chip and silicon work (VLSI, ASIC, RTL, circuit design, design verification, EDA, computer or GPU architecture, firmware) is "hardware". Compilers, math/linear-algebra libraries, simulation and systems software are "backend". "infrastructure" is for cloud, platform, networking, reliability and observability software. Forward Deployed Software Engineer roles are "full-stack". Research on machine-learning models is "ML/AI".
- term: "<Season> <year>" (e.g. "Summer 2027") when the text names a season and a year for the internship itself; just "<year>" (e.g. "2027") when only a year is given; otherwise null. The year must be printed in the text: if the text says only "Summer" with no year, term is "Summer" is NOT allowed, use null. A graduation date is NOT the term. Never put a program name or a date range in term. A start month such as "beginning October 2026" gives no season, so term is "2026".
- season: Summer, Fall, Winter or Spring ONLY if that exact word appears in the text for the internship period. Never convert months to a season (May-August is not stated as "Summer").
- pay_min / pay_max: numbers for the intern pay range exactly as printed (no conversion). pay_currency: ISO code. pay_period: hour, week, month or year as printed. If only one figure is given, set both to it. Ignore salary ranges that are clearly for non-intern roles.
- work_mode: onsite, hybrid or remote, only if the posting states it for THIS role. Company-wide boilerplate (e.g. "many teams offer hybrid options", "some roles allow remote work", "we encourage employees to work from our offices") does NOT count: use null. An office address or a relocation request alone does not state a work mode.
- visa_sponsorship: "yes" or "no" only if the posting explicitly mentions visas or sponsorship. "U.S. Person required", citizenship or clearance requirements are NOT a statement about sponsorship: use null.
- grad_years: who may apply by graduation date/class, copied briefly (e.g. "Class of 2027 or 2028"), else null.
Schema: {"category":str,"term":str|null,"season":str|null,"pay_min":number|null,"pay_max":number|null,"pay_currency":str|null,"pay_period":str|null,"work_mode":str|null,"visa_sponsorship":str|null,"grad_years":str|null}"""

_FIELDS = ["category", "term", "season", "pay_min", "pay_max", "pay_currency", "pay_period",
           "work_mode", "visa_sponsorship", "grad_years"]


def _money_seen(v: float, text: str) -> bool:
    """Is the number v printed somewhere in text (as 45, 45.50, 45,000 or 45k)?"""
    flat = re.sub(r"[,\s]", "", text)
    forms = {f"{v:.2f}".rstrip("0").rstrip("."), f"{v:,.0f}"}
    if v >= 1000 and v % 1000 == 0:
        forms.add(f"{int(v / 1000)}k")
    return any(f in text or f in flat for f in forms if f)


def normalise_term(term: Any) -> str | None:
    """'2027 Internships' -> '2027'; 'Summer 2027' stays; 'May-August, 2027' -> '2027'.
    Always '<Season> <year>' or just '<year>'; None if there is no year."""
    if not isinstance(term, str):
        return None
    year = re.search(r"\b(20\d\d)\b", term)
    if not year:
        return None
    season = re.search(_SEASON, term, re.I)
    if season:
        s = "Fall" if season.group(1).lower() == "autumn" else season.group(1).capitalize()
        return f"{s} {year.group(1)}"
    return year.group(1)


def validate(ans: dict[str, Any], text: str) -> dict[str, Any]:
    """Keep only model answers that are allowed values AND grounded in the description."""
    out: dict[str, Any] = {}
    cat = ans.get("category")
    out["category"] = cat if cat in CATEGORIES else "other"

    season = ans.get("season")
    if isinstance(season, str) and season.capitalize() in ("Summer", "Fall", "Winter", "Spring") \
            and re.search(season, text, re.I):
        out["season"] = season.capitalize()
    term = normalise_term(ans.get("term"))
    if term and "season" not in out:
        # the season word is not in the text (model converted months, e.g. May-August -> Summer):
        # keep only the year, if the year itself is in the text
        term = re.search(r"20\d\d", term).group(0)
    if term and all(w.lower() in text.lower() for w in re.findall(r"[A-Za-z]{4,}|20\d\d", term)):
        out["term"] = term

    lo, hi = ans.get("pay_min"), ans.get("pay_max")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo <= hi \
            and _money_seen(lo, text) and _money_seen(hi, text):
        out.update(pay_min=float(lo), pay_max=float(hi))
        cur, per = ans.get("pay_currency"), ans.get("pay_period")
        out["pay_currency"] = cur if isinstance(cur, str) and re.fullmatch(r"[A-Z]{3}", cur) else None
        out["pay_period"] = per if per in ("hour", "week", "month", "year") else None

    wm = ans.get("work_mode")
    if wm in MODE_WORDS and MODE_WORDS[wm].search(text):   # must be grounded in the text
        out["work_mode"] = wm
    if ans.get("visa_sponsorship") in ("yes", "no") and re.search(r"sponsor|visa|work authori[sz]ation", text, re.I):
        out["visa_sponsorship"] = ans["visa_sponsorship"]
    gy = ans.get("grad_years")
    # must name an actual graduation year (or high school), and every year it names must be in the
    # text. Degree levels ("pursuing a PhD") and "state your graduation date" requirements carry no year.
    if isinstance(gy, str) and re.search(r"\b20\d\d\b|high school", gy, re.I) \
            and all(y in text for y in re.findall(r"\b20\d\d\b", gy)):
        out["grad_years"] = gy.strip()[:120]
    # "February 2027 - August 2027" + season Spring: say "Spring 2027" when the text does
    if out.get("season") and re.fullmatch(r"20\d\d", out.get("term") or ""):
        combo = f"{out['season']} {out['term']}"
        if combo.lower() in text.lower():
            out["term"] = combo
    return out



class LLMExtractor:
    def __init__(self, api_key: str, cache_dir: str | Path = ".cache/llm", max_usd: float = 2.0,
                 model: str = MODEL):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3)
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_usd = max_usd
        self.calls = self.cache_hits = self.failures = 0
        self.in_tokens = self.out_tokens = 0
        self.budget_hit = False
        self.last_error = ""
        self.answers_checked = self.answers_altered = 0   # raw answers the validator had to change
        self.altered: dict[str, int] = {}                 # field -> times its raw value was dropped/changed
        self._lock = threading.Lock()

    def record_validation(self, raw: dict[str, Any], kept: dict[str, Any]) -> None:
        bad = [k for k in _FIELDS if raw.get(k) not in (None, "") and kept.get(k) != raw.get(k)]
        with self._lock:
            self.answers_checked += 1
            self.answers_altered += bool(bad)
            for k in bad:
                self.altered[k] = self.altered.get(k, 0) + 1

    @property
    def cost_usd(self) -> float:
        return self.in_tokens / 1e6 * PRICE_IN_PER_MTOK + self.out_tokens / 1e6 * PRICE_OUT_PER_MTOK

    def _cache_file(self, job: Job) -> Path:
        raw = f"{PROMPT_VERSION}|{self.model}|{job.title}|{job.description[:MAX_DESC_CHARS]}"
        return self.cache_dir / f"{hashlib.sha256(raw.encode()).hexdigest()[:32]}.json"

    def ask(self, job: Job) -> dict[str, Any] | None:
        cf = self._cache_file(job)
        if cf.is_file():
            with self._lock:
                self.cache_hits += 1
            return json.loads(cf.read_text())
        with self._lock:
            if self.cost_usd >= self.max_usd:
                self.budget_hit = True
                return None
        user = f"Title: {job.title}\nLocation: {job.location}\n\nDescription:\n{job.description[:MAX_DESC_CHARS]}"
        try:
            msg = self.client.messages.create(
                model=self.model, max_tokens=400, system=SYSTEM,
                messages=[{"role": "user", "content": user}])
        except Exception as e:  # noqa: BLE001 - any API failure falls back to regex/heuristics
            with self._lock:
                self.failures += 1
                self.last_error = f"{type(e).__name__}: {str(e)[:160]}"
            return None
        with self._lock:
            self.calls += 1
            self.in_tokens += msg.usage.input_tokens
            self.out_tokens += msg.usage.output_tokens
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            ans = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            ans = None
        if not isinstance(ans, dict):
            with self._lock:
                self.failures += 1
                self.last_error = "model reply was not a JSON object"
            return None
        cf.write_text(json.dumps(ans))
        return ans

    def stats(self) -> dict[str, Any]:
        return {"model": self.model, "llm_calls": self.calls, "llm_cache_hits": self.cache_hits,
                "llm_failures": self.failures, "input_tokens": self.in_tokens,
                "output_tokens": self.out_tokens, "cost_usd": round(self.cost_usd, 4),
                "budget_usd": self.max_usd, "budget_hit": self.budget_hit,
                "last_error": self.last_error,
                "answers_altered_by_validator": f"{self.answers_altered}/{self.answers_checked}",
                "fields_altered": dict(self.altered)}


def enrich(job: Job, llm: LLMExtractor | None) -> str:
    """Fill the extracted fields on `job`. Returns 'llm', 'regex' or 'regex+fallback'."""
    text = f"{job.title}\n{job.description}"
    found: dict[str, Any] = {}
    ans = llm.ask(job) if llm else None
    method = "regex"
    if ans:
        found = validate(ans, text)
        llm.record_validation(ans, found)
        method = "llm"
    elif llm:
        method = "regex+fallback"
    # Title is searched too (NVIDIA puts "Summer 2027" only in the title).
    # When the model answered, its null is respected for term/season/mode (the regex cannot tell
    # a graduation date or company boilerplate from the real thing); regex only backs up pay,
    # which is literal text. With no model answer, all regex results are used.
    for k, v in regex_extract(text).items():
        if not ans or k.startswith("pay_"):
            found.setdefault(k, v)
    if not ans:
        found["category"] = heuristic_category(job.title)
    for k in _FIELDS:
        if k in found:
            setattr(job, k, found[k])
    if job.source_work_mode:          # the source's own field beats anything read from the text
        job.work_mode = job.source_work_mode
    return method

