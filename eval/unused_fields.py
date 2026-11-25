"""List fields each source returns that the adapters never read (cache only: no requests).

For every field it shows how many internship postings have a non-empty value and one example,
so you can see what information is being dropped before it ever reaches `description`.
"""
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.classify import TITLE_RE  # noqa: E402

USED = {
    "greenhouse": {"id", "title", "company_name", "location", "first_published", "absolute_url", "content"},
    "lever": {"id", "text", "categories", "createdAt", "hostedUrl", "applyUrl", "descriptionPlain",
              "lists", "additionalPlain"},
    "workday": {"title", "jobReqId", "location", "startDate", "externalUrl", "jobDescription"},
}
seen = defaultdict(Counter)
example = {}
total = Counter()
for f in glob.glob(str(ROOT / ".cache" / "string" / "*.json")):
    d = json.load(open(f))
    data, url = d["data"], d["url"]
    if "greenhouse" in url and isinstance(data, dict) and "jobs" in data:
        src, items, title_key = "greenhouse", [j for j in data["jobs"] if TITLE_RE.search(j["title"])], "title"
    elif "lever" in url and isinstance(data, list):
        src, items, title_key = "lever", [j for j in data if TITLE_RE.search(j["text"])], "text"
    elif isinstance(data, dict) and "jobPostingInfo" in data:
        src, items, title_key = "workday", [data["jobPostingInfo"]], "title"
    else:
        continue
    for j in items:
        total[src] += 1
        for k, v in j.items():
            if k in USED[src] or v in (None, "", [], {}):
                continue
            seen[src][k] += 1
            example.setdefault((src, k), json.dumps(v, ensure_ascii=False)[:150])
for src in ("greenhouse", "lever", "workday"):
    print(f"\n=== {src}: {total[src]} internship postings in cache; fields never read ===")
    for k, n in seen[src].most_common():
        print(f"  {n:4}/{total[src]:<4} {k:28} e.g. {example[(src, k)]}")
