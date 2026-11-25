"""Manual check of the second-run report: mutate state/snapshot.json so the next run has
something to find (one closed, one changed, one 'new'), without spending any requests.

    python tests/tamper_snapshot.py && python -m feed.cli --no-llm
"""
import json
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "state" / "snapshot.json"
snap = json.loads(p.read_text())
keys = sorted(snap["jobs"])
ghost = dict(snap["jobs"][keys[0]], job_id="GHOST-1", title="Ghost Intern (closed since last run)")
snap["jobs"]["stripe:GHOST-1"] = ghost | {"source": "stripe"}      # in snapshot, not on the site -> closed
snap["jobs"][keys[1]]["location"] = "Somewhere Else"                # changed
del snap["jobs"][keys[2]]                                           # on the site, not in snapshot -> new
p.write_text(json.dumps(snap))
print("tampered:", "closed=stripe:GHOST-1", "changed=" + keys[1], "new=" + keys[2])
