"""Check the FINAL records in out/internships.json against each posting's text (cache only).

Mechanical checks per row (category is a judgement call and is NOT checked here):
  term/season  - the words and year appear in the title/description
  pay          - both figures appear in the text; min <= max; period/currency allowed
  work_mode    - a supporting word appears
  visa         - a visa/sponsor word appears
  grad_years   - contains a 4-digit year or 'high school', and that phrase's year is in the text
Prints every violation and the share of rows with at least one.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.client import StringClient  # noqa: E402
from feed.extract import MODE_WORDS, _money_seen  # noqa: E402
from feed.models import CATEGORIES  # noqa: E402
from feed.sources import get_sources  # noqa: E402

rows = {r["company"] + ":" + r["job_id"]: r for r in json.loads((ROOT / "out/internships.json").read_text())["internships"]}
client = StringClient("unused", cache_dir=ROOT / ".cache" / "string", max_requests=0)
bad_rows, checked = 0, 0
for src in get_sources():
    for job in src.fetch(client).jobs:
        r = next((x for x in rows.values() if x["source"] == job.source and x["job_id"] == job.job_id), None)
        if r is None:
            print("MISSING FROM OUTPUT:", job.key)
            continue
        checked += 1
        text = f"{job.title}\n{job.description}"
        low = text.lower()
        v = []
        if r["category"] not in CATEGORIES:
            v.append(f"category {r['category']!r}")
        if r["season"] and r["season"].lower() not in low:
            v.append(f"season {r['season']!r} not in text")
        if r["term"]:
            if not re.fullmatch(r"((Summer|Fall|Winter|Spring) )?20\d\d", r["term"]):
                v.append(f"term format {r['term']!r}")
            elif not all(w.lower() in low for w in r["term"].split()):
                v.append(f"term {r['term']!r} not in text")
        if r["season"] and r["term"] and r["season"] not in r["term"] and re.fullmatch(r"(\w+ )20\d\d", r["term"]):
            v.append(f"season {r['season']} disagrees with term {r['term']}")
        if r["pay_min"] is not None:
            if not (_money_seen(r["pay_min"], text) and _money_seen(r["pay_max"], text)):
                v.append(f"pay {r['pay_min']}-{r['pay_max']} not in text")
            if r["pay_min"] > r["pay_max"]:
                v.append("pay min > max")
            if r["pay_period"] not in ("hour", "week", "month", "year"):
                v.append(f"pay_period {r['pay_period']!r}")
        if r["work_mode"] and r["work_mode"] != job.source_work_mode \
                and not MODE_WORDS[r["work_mode"]].search(text):    # source field OR text must support it
            v.append(f"work_mode {r['work_mode']!r} unsupported")
        if r["visa_sponsorship"] and not re.search(r"sponsor|visa", text, re.I):
            v.append("visa unsupported")
        gy = r["grad_years"]
        if gy:
            if not re.search(r"20\d\d|high school", gy, re.I):
                v.append(f"grad_years has no year: {gy!r}")
            for y in re.findall(r"20\d\d", gy):
                if y not in text:
                    v.append(f"grad_years year {y} not in text")
        if v:
            bad_rows += 1
            print(f"{job.key[:28]:28} {job.title[:40]:40} {v}")
print(f"\nchecked {checked} final rows; rows with a violation: {bad_rows} ({100 * bad_rows / max(checked, 1):.1f}%)")
