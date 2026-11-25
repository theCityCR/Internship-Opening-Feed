"""What counts as an internship, and a cheap offline category guess.

RULE (also written in the README). A posting is an internship if ANY of these hold:
  1. "title"       - the title contains intern / interns / internship(s) / co-op / working student
                     as a whole word ("Internal Tools" and "International" do NOT match).
  2. "structured"  - the source's own structured field says intern (Lever `commitment`,
                     Workday `workerSubType` = Intern).
  3. "description" - the description states it explicitly, e.g. "this internship",
                     "12-week summer internship", "as an intern".
Everything else (new-grad, "University" full-time roles, general mentions of internships
such as "internship experience is a plus") is excluded.
"""
from __future__ import annotations

import re

TITLE_RE = re.compile(r"\b(?:interns?|internships?|co-?ops?|working students?)\b", re.I)

_DESC_PATTERNS = [
    re.compile(r"\bthis\s+(?:[\w-]+\s+){0,3}?(?:internship|co-?op)\b", re.I),
    re.compile(r"\b\d{1,2}[- ]weeks?\s+(?:[\w-]+\s+){0,2}internship\b", re.I),
    re.compile(r"\b(?:join|joining|work)\b[^.\n]{0,40}\bas an? (?:\w+\s+){0,2}intern\b", re.I),
]


def internship_rule(title: str, description: str, structured: bool) -> str | None:
    if TITLE_RE.search(title or ""):
        return "title"
    if structured:
        return "structured"
    if any(p.search(description or "") for p in _DESC_PATTERNS):
        return "description"
    return None


# ---- offline fallback category (used with --no-llm or when the model fails) ----------
_CAT_RULES: list[tuple[str, re.Pattern]] = [
    ("quant", re.compile(r"\bquant|trading|trader", re.I)),
    ("security", re.compile(r"\bsecurity|cyber|infosec|\bcrypto", re.I)),
    ("hardware", re.compile(r"\bhardware|\basic\b|\bfpga|\brtl\b|silicon|circuit|\bchip|firmware|\bdft\b|verification|\bgpu\b.*(arch|design)|embedded|\bvlsi|physical design|computer architecture|\bmechanical|\belectrical", re.I)),
    ("ML/AI", re.compile(r"\bmachine learning|\bml\b|\bai\b|\bllm|deep learning|reinforcement|generative|\bnlp\b|computer vision|research scientist|applied research|\brobotics", re.I)),
    ("data", re.compile(r"\bdata (?:scien|analy|engineer)|analytics|\bbi\b|data platform", re.I)),
    ("mobile", re.compile(r"\bios\b|android|\bmobile", re.I)),
    ("frontend", re.compile(r"front-?end|\bui\b engineer|\bweb developer", re.I)),
    ("infrastructure", re.compile(r"infrastructure|\bsre\b|reliability|devops|platform engineer|cloud|\bnetwork|kernel|compiler|systems? (?:software|engineer)", re.I)),
    ("backend", re.compile(r"back-?end|\bapi\b|server", re.I)),
    ("full-stack", re.compile(r"full-?stack|forward deployed", re.I)),
]


def heuristic_category(title: str) -> str:
    for cat, rx in _CAT_RULES:
        if rx.search(title or ""):
            return cat
    return "other"
