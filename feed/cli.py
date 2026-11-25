"""CLI: python -m feed.cli [--sources stripe,nvidia] [--no-llm] [--html out/index.html] ..."""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import render
from .client import BudgetExceeded, FetchError, StringClient
from .diff import build_snapshot, compute_diff, load_snapshot, save_snapshot
from .env import load_env
from .extract import LLMExtractor, enrich
from .models import SourceResult
from .sources import get_sources


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="internship-feed", description=__doc__)
    ap.add_argument("--sources", help="comma-separated source names (default: all)")
    ap.add_argument("--no-llm", action="store_true", help="regex + keyword rules only, no Claude calls")
    ap.add_argument("--max-requests", type=int, default=150, help="String request budget")
    ap.add_argument("--max-usd", type=float, default=2.0, help="Claude spend cap for this run")
    ap.add_argument("--out", default="out/internships.json")
    ap.add_argument("--html", default="out/index.html", help="'' to skip")
    ap.add_argument("--state", default="state/snapshot.json")
    ap.add_argument("--no-state", action="store_true", help="do not read or write the snapshot")
    ap.add_argument("--fresh", action="store_true", help="ignore the on-disk String cache")
    ap.add_argument("--limit", type=int, default=40, help="rows shown in the terminal table")
    args = ap.parse_args(argv)

    load_env()
    key = os.environ.get("STRING_API_KEY")
    if not key:
        print("STRING_API_KEY is not set (put it in .env, see README).", file=sys.stderr)
        return 2
    client = StringClient(key, max_requests=args.max_requests,
                          cache_dir=None if args.fresh else ".cache/string")
    llm = None
    if not args.no_llm:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set; use --no-llm or add it to .env.", file=sys.stderr)
            return 2
        llm = LLMExtractor(os.environ["ANTHROPIC_API_KEY"], max_usd=args.max_usd)

    results: list[SourceResult] = []
    for src in get_sources(args.sources.split(",") if args.sources else None):
        try:
            results.append(src.fetch(client))
        except (FetchError, BudgetExceeded) as e:
            print(f"[{src.name}] FAILED: {e}", file=sys.stderr)
            results.append(SourceResult(src.name, src.company, scope="failed", notes=[str(e)]))

    jobs = [j for r in results for j in r.jobs]
    seen, unique = set(), []
    for j in jobs:                      # same posting listed twice under one key -> keep once
        if j.key not in seen:
            seen.add(j.key)
            unique.append(j)
    jobs = unique

    methods: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for m in ex.map(lambda j: enrich(j, llm), jobs):
            methods[m] = methods.get(m, 0) + 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {"generated_at": now, "sources": [
        {"name": r.name, "scope": r.scope, "site_total": r.site_total, "read": r.fetched_total,
         "internships": len(r.jobs), "complete": r.complete, "rule_counts": r.rule_counts,
         "string_requests": r.string_requests, "notes": r.notes} for r in results]}
    records = render.write_json(args.out, jobs, meta)
    if args.html:
        render.write_html(args.html, records, meta)

    print(render.table(records, args.limit))
    print("\n== Source completeness (site total vs. postings read) ==")
    for r in results:
        flag = "OK " if r.complete else "GAP"
        print(f"{flag} {r.name:9} scope={r.scope!r} site_total={r.site_total} read={r.fetched_total} "
              f"internships={len(r.jobs)} rules={r.rule_counts} string_requests={r.string_requests}")
        for n in r.notes[:3]:
            print(f"      note: {n}")

    if not args.no_state:
        old = load_snapshot(args.state)
        diff = compute_diff(old, jobs, results)
        print("\n== Changes since last run ==")
        if diff["first_run"]:
            print("first run: no previous snapshot to compare with")
        else:
            print(f"new={len(diff['new'])} closed={len(diff['closed'])} changed={len(diff['changed'])} "
                  f"carried_over(incomplete source)={len(diff['carried_over_incomplete_source'])}")
            for k in diff["new"][:10]:
                print(f"  + {k}")
            for k, rec in list(diff["closed_records"].items())[:10]:
                print(f"  - {k}  {rec['title']}")
            for k, d in list(diff["changed"].items())[:10]:
                print(f"  ~ {k}  {', '.join(d)}")
        save_snapshot(args.state, build_snapshot(old, jobs, diff, now))

    print("\n== Cost ==")
    print(f"String requests: {client.requests_made}/{client.max_requests} "
          f"(cache hits, free: {client.cache_hits}; by type: {client.by_type})")
    if llm:
        print(f"Claude: {llm.stats()}")
    print(f"Extraction methods: {methods}")
    print(f"Total internships: {len(jobs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
