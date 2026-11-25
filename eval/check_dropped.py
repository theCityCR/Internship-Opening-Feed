"""Cache-only checks on information the adapters drop (no requests, no API calls)."""
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.classify import TITLE_RE  # noqa: E402
from feed.sources.lever import _lever_text  # noqa: E402
from feed.text import html_to_text  # noqa: E402


def norm(s):
    return re.sub(r"\W+", "", s.lower())


for f in glob.glob(str(ROOT / ".cache" / "string" / "*.json")):
    d = json.load(open(f))
    data, url = d["data"], d["url"]
    if "lever" in url and isinstance(data, list):
        print("== Lever workplaceType over ALL", len(data), "postings:", dict(Counter(j.get("workplaceType") for j in data)))
        interns = [j for j in data if TITLE_RE.search(j["text"])]
        print("   interns:", dict(Counter(j.get("workplaceType") for j in interns)))
        # does boilerplate text contradict 'onsite' (is the field a default?)
        print("   non-intern roles by workplaceType x country:",
              dict(Counter((j.get("workplaceType"), j.get("country")) for j in data).most_common(6)))
        # is each Lever text part already inside my description?
        miss = Counter()
        for j in interns:
            mine = norm(_lever_text(j))
            for part in ("openingPlain", "descriptionBodyPlain", "additionalPlain", "descriptionPlain"):
                t = norm(j.get(part) or "")
                if t and t[:300] not in mine:
                    miss[part] += 1
        print("   Lever parts whose text is NOT in my description (of", len(interns), "):", dict(miss) or "none")
        lens = [(len(_lever_text(j)), len(j.get("descriptionPlain") or "")) for j in interns]
        print("   my description chars vs raw descriptionPlain chars (first 3):", lens[:3])
    elif "greenhouse" in url and isinstance(data, dict) and "jobs" in data:
        ints = [j for j in data["jobs"] if TITLE_RE.search(j["title"])]
        print("== Greenhouse: location string vs offices")
        for j in ints[:20]:
            offs = [o.get("location") or o.get("name") for o in j.get("offices", [])]
            if len(offs) != len((j["location"]["name"] or "").split(",")) or len(offs) > 1:
                print("   ", j["title"][:34], "| location:", j["location"]["name"], "| offices:", offs)
        print("   departments:", Counter(dd["name"] for j in ints for dd in j.get("departments", [])).most_common(4))
        print("   education:", dict(Counter(j.get("education") for j in ints)))
        diff = sum(1 for j in ints if (j.get("updated_at") or "")[:10] != (j.get("first_published") or "")[:10])
        print("   updated_at differs from first_published for", diff, "of", len(ints))
    elif isinstance(data, dict) and "jobPostingInfo" in data:
        i = data["jobPostingInfo"]
        if i.get("additionalLocations"):
            print("== Workday multi-location example:", i["title"][:40], "| location:", i["location"], "| additional:", i["additionalLocations"])
