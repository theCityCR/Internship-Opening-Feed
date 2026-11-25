"""Output: CLI table, JSON feed, and a small static HTML page."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .models import Job

_COLS = [("Company", "company", 10), ("Role", "title", 42), ("Location", "location", 24),
         ("Posted", "date_posted", 10), ("Cat", "category", 14), ("Term", "term", 12),
         ("Pay", "pay", 22), ("Mode", "work_mode", 7), ("ID", "job_id", 12)]


def pay_text(j: dict[str, Any]) -> str:
    if j.get("pay_min") is None:
        return ""
    cur = {"USD": "$", "GBP": "£", "EUR": "€"}.get(j.get("pay_currency") or "", (j.get("pay_currency") or "") + " ")
    def f(v): return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"
    rng = f"{cur}{f(j['pay_min'])}" + ("" if j["pay_min"] == j["pay_max"] else f"-{f(j['pay_max'])}")
    return rng + (f"/{j['pay_period']}" if j.get("pay_period") else "")


def table(records: list[dict[str, Any]], limit: int | None = None) -> str:
    rows = records[:limit] if limit else records
    def cell(r, key, w):
        v = pay_text(r) if key == "pay" else (r.get(key) or "")
        v = str(v).replace("\n", " ")
        return v if len(v) <= w else v[: w - 1] + "…"
    lines = [" | ".join(h.ljust(w) for h, _, w in _COLS), "-+-".join("-" * w for _, _, w in _COLS)]
    for r in rows:
        lines.append(" | ".join(cell(r, k, w).ljust(w) for _, k, w in _COLS))
    if limit and len(records) > limit:
        lines.append(f"... {len(records) - limit} more (see out/internships.json)")
    return "\n".join(lines)


def write_json(path: str | Path, jobs: list[Job], meta: dict[str, Any]) -> list[dict[str, Any]]:
    records = sorted((j.to_record() for j in jobs), key=lambda r: (r["company"], r["category"], r["title"]))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"meta": meta, "internships": records}, indent=1, ensure_ascii=False))
    return records


def write_html(path: str | Path, records: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    e = html.escape
    body = []
    for r in records:
        body.append(
            "<tr data-cat='{c}' data-co='{co}'><td>{co}</td><td><a href='{u}' rel='noopener'>{t}</a></td>"
            "<td>{l}</td><td>{d}</td><td>{c}</td><td>{te}</td><td>{p}</td><td>{m}</td></tr>".format(
                co=e(r["company"]), u=e(r["apply_url"], quote=True), t=e(r["title"]), l=e(r["location"]),
                d=e(r["date_posted"] or ""), c=e(r["category"]), te=e(r["term"] or ""),
                p=e(pay_text(r)), m=e(r["work_mode"] or "")))
    cats = sorted({r["category"] for r in records})
    opts = "".join(f"<option>{e(c)}</option>" for c in cats)
    page = f"""<!doctype html><meta charset=utf-8><title>Internship openings</title>
<style>body{{font:14px system-ui;margin:2rem}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #ddd;padding:6px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#fff}}</style>
<h1>Internship openings ({len(records)})</h1>
<p>Generated {e(str(meta.get('generated_at', '')))}. Read-only view of company careers pages; follow the link to apply on the company's site.</p>
<label>Category <select id=f><option value=''>all</option>{opts}</select></label>
<input id=q placeholder='filter text' style='margin-left:1rem'>
<table><thead><tr><th>Company<th>Role<th>Location<th>Posted<th>Category<th>Term<th>Pay<th>Mode</tr></thead>
<tbody id=b>{''.join(body)}</tbody></table>
<script>const f=document.getElementById('f'),q=document.getElementById('q');
function go(){{for(const r of document.querySelectorAll('#b tr'))
r.hidden=!((!f.value||r.dataset.cat===f.value)&&r.textContent.toLowerCase().includes(q.value.toLowerCase()))}}
f.onchange=q.oninput=go</script>"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(page)
