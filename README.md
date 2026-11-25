# Internship openings feed

One normalised list of software internship openings, read from companies' own careers backends
through the [String Web Access](https://docs.usestring.ai) API. Read-only: it never applies, logs in or submits anything.

| Company | Source | Type |
|---|---|---|
| Stripe | Greenhouse board API | hosted job board |
| Palantir | Lever postings API | hosted job board |
| NVIDIA | Workday (`nvidia.wd5.myworkdayjobs.com`) | **not** Greenhouse/Lever |

Every row has: company, role, location, date posted, apply link, source job ID, one category
(backend, frontend, full-stack, mobile, ML/AI, data, infrastructure, security, quant, hardware, other),
plus term/season, pay range, work mode, visa sponsorship and graduation years. A field is empty when the text doesn't say.

## Setup

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
printf 'STRING_API_KEY=...\nANTHROPIC_API_KEY=...\n' > .env     # .env is gitignored
```

## Run

```sh
.venv/bin/python -m feed.cli              # full run: String + Claude (claude-haiku-4-5)
.venv/bin/python -m feed.cli --no-llm     # regex/keyword rules only, no Claude calls
.venv/bin/python -m feed.cli --sources nvidia --max-requests 100 --max-usd 1
.venv/bin/python -m pytest                # offline tests from saved responses
.venv/bin/python eval/run_eval.py         # extraction accuracy vs eval/labels.json
```

Output: a table in the terminal, `out/internships.json`, and a filterable page `out/index.html`.
Each run prints per-source completeness, String requests used (budget 150), Claude tokens and dollars (cap $2).
Responses are cached in `.cache/` so re-runs cost nothing; `--fresh` bypasses the String cache.

### Second run: new / closed / changed
`state/snapshot.json` is compared with the current run and the report lists new, closed and changed openings
("changed" = title, location, date, link or description text). A source that failed or came back incomplete is
**never** reported as closed; its old openings are carried over.

## What counts as an internship (the rule)
A posting is included if any of these hold:
1. **title**: contains the whole word intern / interns / internship(s) / co-op / working student ("Internal Tools" doesn't match);
2. **structured**: the source's own field says intern (Lever `commitment`; Workday job type "Intern (Fixed Term)");
3. **description**: it states it explicitly ("this internship", "12-week ... internship").

Not included: new-grad roles, full-time "University" roles, and passing mentions ("internship experience is a plus").
The per-source counts of which rule fired are printed. On the current data 140 of 141 hits are by title; the one
non-title hit is Palantir's "Meritocracy Fellowship" (Lever `commitment: Internship`), a business-development role
rather than a software one. The tool does not filter by discipline, so non-engineering internships are listed under
category `other`. The `description` rule is unit-tested but has not matched anything on live data.

## How extraction works
Regexes handle literal text (pay figures, "Summer 2027"). One Claude call per posting returns JSON; every answer is
then checked against the description (a pay figure, season or term that isn't literally in the text is dropped, categories
must be one of the 11) and company-wide boilerplate ("many teams offer hybrid options") is not accepted as a work mode.
If Claude fails or the cap is hit, regexes and title keywords are used instead.

## Known gaps
See `NOTE.md` for the numbers behind these.
- **NVIDIA covers US postings only** (75 of the 234 global intern postings). All 234 need about 250 requests, over the 150 budget. The tool reports 75/75 for its scope; the scope itself is a choice.
- **Stripe and Palantir have no site-stated total to cross-check**: Greenhouse reports `meta.total` (checked), Lever doesn't (complete by construction, not verified).
- Non-title internships: only one found (the Palantir fellowship above), via a structured field. Roles that are internships in everything but name and have no such field would be missed.
- Not filtered to software roles: design, marketing, finance etc. internships are included as category `other` (32 of 141).
- `visa_sponsorship` is empty for all 141 postings because none of them state a sponsorship position; that is expected, not verified against a labelled example.
- Date posted: Greenhouse `first_published`, Lever `createdAt`, Workday `startDate` (the "posted on" date); sources define "posted" differently.
- Postings with several locations are one row (Stripe lists them in one string); NVIDIA postings with "2 Locations" show only the primary location.
- Pay: a posting with several location-specific ranges gets one range (the first found), not a per-location one.
- Visa/graduation-year fields are model-extracted and **not** covered by the accuracy measurement.
- No retries beyond 3 per request; Workday rate-limiting at larger scale is untested.
- Hand labels in `eval/labels.json` were drafted by an AI and need human verification (see `NOTE.md`).

## License
MIT
