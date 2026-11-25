"""Pick 15 postings (5 per company, spread across the list) for hand-labelling.

Uses the on-disk String cache, so it costs no Web Access requests when a run has been done.
Writes eval/samples.json (id, title, description). Labels live separately in eval/labels.json.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.client import StringClient  # noqa: E402
from feed.env import load_env  # noqa: E402
from feed.sources import get_sources  # noqa: E402

load_env(ROOT / ".env")
client = StringClient(os.environ["STRING_API_KEY"], cache_dir=ROOT / ".cache" / "string", max_requests=0)
samples = []
for src in get_sources():
    jobs = src.fetch(client).jobs          # max_requests=0: any cache miss raises, so no spend
    step = max(1, len(jobs) // 5)
    for j in jobs[::step][:5]:
        samples.append({"id": j.key, "title": j.title, "location": j.location, "description": j.description})
(ROOT / "eval" / "samples.json").write_text(json.dumps(samples, indent=1, ensure_ascii=False))
print(len(samples), "samples;", client.stats())
