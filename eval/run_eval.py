"""Score extraction against eval/labels.json: regex-only vs. regex + Claude.

    python eval/run_eval.py            # uses the Claude key; ~15 calls, a few cents
    python eval/run_eval.py --no-llm   # regex only, free

A field is correct when the extracted value equals the label (None == None counts: the text
did not say, and the tool said nothing). Prints per-field accuracy and every mismatch.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feed.env import load_env  # noqa: E402
from feed.extract import LLMExtractor, enrich  # noqa: E402
from feed.models import Job  # noqa: E402

FIELDS = ["term", "season", "pay_min", "pay_max", "pay_period", "work_mode"]


def run(samples, labels, llm):
    wrong, correct = [], {f: 0 for f in FIELDS}
    for s in samples:
        job = Job(source="", company="", job_id=s["id"], title=s["title"], location=s["location"],
                  date_posted=None, apply_url="", description=s["description"])
        enrich(job, llm)
        for f in FIELDS:
            got, want = getattr(job, f), labels[s["id"]][f]
            if got == want:
                correct[f] += 1
            else:
                wrong.append((s["id"], f, want, got))
    return correct, wrong


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()
    load_env(ROOT / ".env")
    samples = json.loads((ROOT / "eval" / "samples.json").read_text())
    labels = json.loads((ROOT / "eval" / "labels.json").read_text())["labels"]
    assert {s["id"] for s in samples} == set(labels), "samples.json and labels.json disagree"
    n = len(samples)
    modes = [("regex only", None)]
    if not args.no_llm:
        modes.append(("regex + Claude", LLMExtractor(os.environ["ANTHROPIC_API_KEY"], cache_dir=ROOT / ".cache" / "llm")))
    for name, llm in modes:
        correct, wrong = run(samples, labels, llm)
        total = sum(correct.values())
        print(f"\n=== {name}: {total}/{n * len(FIELDS)} field values correct ({100 * total / (n * len(FIELDS)):.0f}%) ===")
        for f in FIELDS:
            print(f"  {f:11} {correct[f]}/{n}")
        for sid, f, want, got in wrong:
            print(f"  MISS {sid} {f}: label={want!r} got={got!r}")
        if llm:
            print("  ", llm.stats())


if __name__ == "__main__":
    main()
