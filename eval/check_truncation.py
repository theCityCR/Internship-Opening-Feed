"""Does the 7000-char cut hide facts from the model? (cache only: no String requests, no API calls)

For every internship it reports descriptions longer than the cut and whether the regex-visible
pay figure or a term sits only beyond the cut.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.client import StringClient  # noqa: E402
from feed.extract import MAX_DESC_CHARS, regex_extract  # noqa: E402
from feed.sources import get_sources  # noqa: E402

client = StringClient("unused", cache_dir=ROOT / ".cache" / "string", max_requests=0)
n = long = pay_lost = term_lost = 0
lengths = []
for src in get_sources():
    for job in src.fetch(client).jobs:
        n += 1
        lengths.append(len(job.description))
        if len(job.description) > MAX_DESC_CHARS:
            long += 1
            full, head = regex_extract(job.description), regex_extract(job.description[:MAX_DESC_CHARS])
            if "pay_min" in full and "pay_min" not in head:
                pay_lost += 1
                print("PAY ONLY AFTER CUT:", job.key, job.title[:50], len(job.description))
            if "term" in full and "term" not in head:
                term_lost += 1
lengths.sort()
print(f"{n} postings; median {lengths[n // 2]} chars, max {lengths[-1]}; "
      f"over {MAX_DESC_CHARS}: {long}; pay only after the cut: {pay_lost}; term only after the cut: {term_lost}")
