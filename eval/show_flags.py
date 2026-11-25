"""Print each flagged answer with the text around the disputed value (reading aid for the audit)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.client import StringClient  # noqa: E402
from feed.extract import LLMExtractor  # noqa: E402
from feed.sources import get_sources  # noqa: E402

only = sys.argv[1] if len(sys.argv) > 1 else ""
flags = {f["id"]: f for f in json.loads((ROOT / "eval" / "audit_flags.json").read_text())}
client = StringClient("unused", cache_dir=ROOT / ".cache" / "string", max_requests=0)
KEY = {"work_mode": r"remote|hybrid|on-?site|office|in-person", "season": r"summer|fall|winter|spring|autumn",
       "visa": r"visa|sponsor|authori", "pay": r"\$|usd|salary|hourly|per (hour|month)", "term": r"20\d\d"}
for src in get_sources():
    for job in src.fetch(client).jobs:
        f = flags.get(job.key)
        if not f or (only and only not in " ".join(f["problems"])):
            continue
        print(f"\n### {job.key} | {job.title}")
        for p in f["problems"]:
            print("  PROBLEM:", p)
        print("  RAW:", {k: v for k, v in f["raw"].items() if v is not None})
        for p in f["problems"]:
            m = re.match(r"(?:ungrounded|regex-disagree|format):(\w+)", p)
            field = m.group(1) if m else "pay"
            pat = KEY.get(field.split("_")[0] if field.startswith("pay") else field, KEY["term"])
            pat = KEY["pay"] if field.startswith("pay") else KEY.get(field, KEY["term"])
            if field == "visa_sponsorship":
                pat = KEY["visa"]
            text = f"{job.title}\n{job.description}"
            for mm in list(re.finditer(pat, text, re.I))[:2]:
                print("     ctx:", " ".join(text[max(0, mm.start() - 130):mm.end() + 130].split()))
