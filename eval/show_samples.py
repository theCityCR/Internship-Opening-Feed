"""Reading aid for hand-labelling: prints each sample's lines that mention the target fields.

It deliberately shows ONLY keyword-bearing lines (not model output) so labels come from the text.
Limitation: a fact stated without any of these keywords would not be shown; labelers should open
the full text in eval/samples.json when a line looks cut off.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = re.compile(r"20\d\d|summer|fall|winter|spring|\$|usd|salary|hourly|stipend|per (hour|month|week|year)|"
                 r"remote|hybrid|on-?site|in[- ]office|in[- ]person|visa|sponsor|work authori|graduat|"
                 r"class of|enrolled|currently pursuing|degree|weeks|months", re.I)
lo = int(sys.argv[1]) if len(sys.argv) > 1 else 0
hi = int(sys.argv[2]) if len(sys.argv) > 2 else 15
for i, s in enumerate(json.loads((ROOT / "eval" / "samples.json").read_text())[lo:hi], lo):
    print(f"\n##### [{i}] {s['id']} | {s['title']} | {s['location']}")
    seen = set()
    for line in re.split(r"\n+", s["description"]):
        for sent in re.split(r"(?<=[.!?])\s+", line):
            if KEY.search(sent) and sent not in seen and len(sent) < 400:
                seen.add(sent)
                print("  >", sent.strip())
