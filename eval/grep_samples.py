"""Show context around a regex in each sample's FULL description (labelling aid)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
pat = re.compile(sys.argv[1], re.I)
for i, s in enumerate(json.loads((ROOT / "eval" / "samples.json").read_text())):
    hits = [" ".join(s["description"][max(0, m.start() - 110):m.end() + 110].split())
            for m in pat.finditer(s["description"])][:2]
    print(f"[{i}] {s['id']} | {s['title'][:50]}")
    for h in hits:
        print("     ..." + h + "...")
