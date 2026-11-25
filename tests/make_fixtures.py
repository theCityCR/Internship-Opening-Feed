"""Trim real cached String responses into small fixtures for offline tests.

Run once after a live run:  python tests/make_fixtures.py
Reads .cache/string/*.json (written by the String client) and writes tests/fixtures/*.json.
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.classify import TITLE_RE  # noqa: E402  (same whole-word rule the product uses)

OUT = ROOT / "tests" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

wrote = set()
for f in glob.glob(str(ROOT / ".cache" / "string" / "*.json")):
    d = json.load(open(f))
    data, url = d["data"], d["url"]
    if "greenhouse" in url and isinstance(data, dict) and "jobs" in data and "greenhouse_stripe" not in wrote:
        interns = [j for j in data["jobs"] if TITLE_RE.search(j["title"])][:3]
        others = [j for j in data["jobs"] if not TITLE_RE.search(j["title"])][:2]
        keep = interns + others
        (OUT / "greenhouse_stripe.json").write_text(json.dumps({"jobs": keep, "meta": {"total": len(keep)}}, indent=1))
        wrote.add("greenhouse_stripe")
    elif "lever" in url and isinstance(data, list) and "lever_palantir" not in wrote:
        interns = [j for j in data if TITLE_RE.search(j["text"])][:3]
        others = [j for j in data if not TITLE_RE.search(j["text"])][:2]
        (OUT / "lever_palantir.json").write_text(json.dumps(interns + others, indent=1))
        wrote.add("lever_palantir")
    elif isinstance(data, dict) and "jobPostingInfo" in data and "workday_detail" not in wrote:
        (OUT / "workday_detail.json").write_text(json.dumps(data, indent=1))
        wrote.add("workday_detail")
print(sorted(wrote))
