"""Audit every cached raw Claude answer (no API calls, no String requests).

For each posting it checks the RAW model JSON against:
  schema    - all keys present, right types, allowed enum values
  grounding - validate() would drop/alter a value because the text does not support it
  regex     - the model disagrees with the literal-text regexes on pay / term
and writes eval/audit_flags.json with every flagged posting for a human to read.

    python eval/audit_llm.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.client import StringClient  # noqa: E402
from feed.env import load_env  # noqa: E402
from feed.extract import (LLMExtractor, MODEL_FIELDS, _FIELDS, apply_evidence, normalise_term,  # noqa: E402
                          regex_extract, validate)
from feed.models import CATEGORIES  # noqa: E402
from feed.sources import get_sources  # noqa: E402

import argparse  # noqa: E402
import feed.extract as _extract  # noqa: E402

_ap = argparse.ArgumentParser()
_ap.add_argument("--prompt", help="audit the cached answers of an older prompt version, e.g. v2")
_ap.add_argument("--cap", type=int, help="description cut that older version used (v2: 7000)")
_args = _ap.parse_args()
if _args.prompt:
    _extract.PROMPT_VERSION = _args.prompt        # _cache_file reads these module globals
if _args.cap:
    _extract.MAX_DESC_CHARS = _args.cap

load_env(ROOT / ".env")
client = StringClient("unused", cache_dir=ROOT / ".cache" / "string", max_requests=0)  # cache only
llm = LLMExtractor("unused", cache_dir=ROOT / ".cache" / "llm")

PERIODS = {"hour", "week", "month", "year", None}
MODES = {"onsite", "hybrid", "remote", None}
rows, flags = 0, []
kinds = Counter()
for src in get_sources():
    for job in src.fetch(client).jobs:
        cf = llm._cache_file(job)
        if not cf.is_file():
            kinds["no_cached_answer"] += 1
            flags.append({"id": job.key, "title": job.title, "problems": ["no_cached_answer"]})
            continue
        rows += 1
        raw = json.loads(cf.read_text())
        text = f"{job.title}\n{job.description}"
        problems = []
        has_evidence = "evidence" in raw            # prompt v7+ returns quoted evidence, no grad_years
        expected = (set(MODEL_FIELDS) | {"evidence"}) if has_evidence else set(_FIELDS)
        if set(raw) != expected:
            problems.append(f"schema:keys {sorted(expected ^ set(raw))}")
        if raw.get("category") not in CATEGORIES:
            problems.append(f"schema:category {raw.get('category')!r}")
        if raw.get("pay_period") not in PERIODS:
            problems.append(f"schema:pay_period {raw.get('pay_period')!r}")
        if raw.get("work_mode") not in MODES:
            problems.append(f"schema:work_mode {raw.get('work_mode')!r}")
        for k in ("pay_min", "pay_max"):
            if raw.get(k) is not None and not isinstance(raw[k], (int, float)):
                problems.append(f"schema:{k} type {type(raw[k]).__name__}")
        if raw.get("term") is not None and raw["term"] != normalise_term(raw["term"]):
            problems.append(f"format:term {raw['term']!r} (normalised to {normalise_term(raw['term'])!r})")
        # Same value checks for every prompt version (no evidence requirement here), then the
        # evidence checks on top for v7+.
        ok = validate(raw, text, require_evidence=False)
        if has_evidence:
            ev = raw["evidence"] if isinstance(raw["evidence"], dict) else {}
            kept = apply_evidence(raw, text)
            for k, vals in (("term", ("term",)), ("season", ("season",)),
                            ("pay", ("pay_min", "pay_max")), ("work_mode", ("work_mode",)),
                            ("visa_sponsorship", ("visa_sponsorship",))):
                if any(raw.get(v) is not None for v in vals) and all(kept.get(v) is None for v in vals):
                    q = ev.get(k)
                    why = "missing" if not q else (
                        "quote not in text" if _extract._squash(q) not in _extract._squash(text)
                        else "quote does not contain the value")
                    problems.append(f"evidence:{k} {why} {(q or '')[:50]!r}")
        for k in ("season", "term", "pay_min", "pay_max", "work_mode", "visa_sponsorship", "grad_years"):
            rv = raw.get(k)
            if k == "term":
                rv = normalise_term(rv)
            if rv not in (None, "") and ok.get(k) != rv:
                problems.append(f"ungrounded:{k} {raw.get(k)!r}")
        rx = regex_extract(text)
        # SOFT flag. The regex takes the FIRST pay range; postings with one range per location make
        # a model that reports the overall range disagree with it without being wrong. So a
        # disagreement is only "soft" when the model's range fully covers the regex's range.
        for k in ("pay_min", "pay_max", "pay_period"):
            if k in rx and raw.get(k) != rx[k]:
                covers = (k in ("pay_min", "pay_max") and raw.get("pay_min") is not None
                          and raw["pay_min"] <= rx["pay_min"] and raw["pay_max"] >= rx["pay_max"])
                problems.append(f"{'soft-' if covers else ''}regex-disagree:{k} model={raw.get(k)!r} regex={rx[k]!r}")
        if "pay_min" not in raw or (raw.get("pay_min") is None and "pay_min" in rx):
            problems.append("missed-pay-the-regex-found")
        if problems:
            flags.append({"id": job.key, "title": job.title, "problems": problems,
                          "raw": raw})
            for p in problems:
                kinds[p.split(" ")[0]] += 1
print(f"audited {rows} cached answers; flagged {len(flags)} ({100 * len(flags) / max(rows, 1):.1f}%)")
# grad_years is no longer asked of the model from v7, so also show the older versions without it:
# that is the like-for-like comparison.
def hard(f, skip_grad=False):
    return [p for p in f["problems"] if not p.startswith("soft-") and not (skip_grad and "grad_years" in p)]


strict = [f for f in flags if hard(f)]
no_grad = [f for f in flags if hard(f, skip_grad=True)]
print(f"  flagged, counting EVERY problem incl. soft regex disagreements: {len(flags)} ({100 * len(flags) / max(rows, 1):.1f}%)")
print(f"  flagged, excluding soft disagreements (model range covers regex range): {len(strict)} ({100 * len(strict) / max(rows, 1):.1f}%)")
print(f"  same, and ignoring grad_years (v7+ does not ask the model): {len(no_grad)} ({100 * len(no_grad) / max(rows, 1):.1f}%)")
for k, v in kinds.most_common():
    print(f"  {v:4}  {k}")
(ROOT / "eval" / "audit_flags.json").write_text(json.dumps(flags, indent=1, ensure_ascii=False))
