"""Reading aid: dump the raw model answer fields the audit cannot check mechanically.

    python eval/review_fields.py category     # title -> category, grouped, for a human to judge
    python eval/review_fields.py grad         # grad_years answer next to the sentence it came from
    python eval/review_fields.py text <job-key> <regex>   # grep one posting's full text
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.client import StringClient  # noqa: E402
from feed.extract import LLMExtractor  # noqa: E402
from feed.sources import get_sources  # noqa: E402

client = StringClient("unused", cache_dir=ROOT / ".cache" / "string", max_requests=0)
llm = LLMExtractor("unused", cache_dir=ROOT / ".cache" / "llm")
mode = sys.argv[1]
seen = set()
for src in get_sources():
    for job in src.fetch(client).jobs:
        raw = json.loads(llm._cache_file(job).read_text())
        if mode == "category":
            k = (job.title, raw["category"])
            if k not in seen:
                seen.add(k)
                print(f"{raw['category']:15} | {job.company[:8]:8} | {job.title}")
        elif mode == "grad" and raw.get("grad_years"):
            m = re.search(r"graduat|class of|20(2[6-9]|3\d)", job.description, re.I)
            ctx = " ".join(job.description[max(0, m.start() - 70):m.end() + 90].split()) if m else "NO MATCH"
            k = (raw["grad_years"], ctx)
            if k not in seen:
                seen.add(k)
                print(f"{job.key[:22]:22} model={raw['grad_years']!r}\n{'':22} text ...{ctx}...")
        elif mode == "mode" and raw.get("work_mode"):
            m = re.search(r"remote|hybrid|on-?site|in[- ]office|in[- ]person|office", job.description, re.I)
            ctx = " ".join(job.description[max(0, m.start() - 100):m.end() + 100].split()) if m else "NO MATCHING WORD"
            print(f"{job.key[:24]:24} model={raw['work_mode']:7} | {job.title[:44]}\n{'':24} ctx ...{ctx}...")
        elif mode == "term" and raw.get("term") is not None:
            print(f"{job.key[:24]:24} term={raw['term']!r:48} season={raw.get('season')!r} | {job.title[:50]}")
        elif mode == "text" and job.key == sys.argv[2]:
            for mm in list(re.finditer(sys.argv[3], job.description, re.I))[:4]:
                print("  ..." + " ".join(job.description[max(0, mm.start() - 120):mm.end() + 120].split()))
            print("  (matches:", len(re.findall(sys.argv[3], job.description, re.I)), ")")
