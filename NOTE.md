# Hand-in note

Repo: https://github.com/theCityCR/Internship-Opening-Feed (MIT)

Setup: String Web Access key for all fetches; the provided Claude key for extraction (`claude-haiku-4-5`).
Cost figures use the Haiku 4.5 list price I assumed in `feed/extract.py` ($1 / $5 per million tokens), not a billed amount.

## What I built
A Python CLI that reads internship postings from three companies' own careers backends through String Web Access,
normalises them (company, role, location, date posted, apply link, source job ID, one category), extracts term/season,
pay, work mode, visa sponsorship and graduation years, and writes a terminal table, `out/internships.json` and `out/index.html`.

- **Stripe**: Greenhouse board API (one request).
- **Palantir**: Lever postings API (one request).
- **NVIDIA**: Workday (not Greenhouse/Lever): paged search plus one detail request per posting.
- A second run reports new / closed / changed openings from `state/snapshot.json`.

## Checks run and results
| Check | Result |
|---|---|
| Unit tests from saved real responses (`pytest`) | 48 passed, including the Claude call with a fake client |
| Customer claim "1 in 10 LLM JSON is wrong" (`eval/audit_llm.py`, all 141 raw answers, mechanical checks) | **Confirmed for the raw JSON** with the first prompt (14.9%). After adding quoted evidence the flag rate is 7.8% counting everything, 3.5% excluding soft pay disagreements (see the section below for how far to trust that). After the validator, the final rows have 0 violations of the same checks (`eval/check_output.py`) |
| Completeness vs site total | Stripe 772/772 read (Greenhouse `meta.total`), NVIDIA 75/75 read (Workday `total`, 4 pages), Palantir 305 read (Lever states no total, so not cross-checked) |
| Internships found | 141 (Stripe 20, Palantir 46, NVIDIA 75) |
| Rows with source ID and apply link | 141/141 |
| Cost of the full run | 82 String requests (budget 150); about 89 across the whole session, including probes. Claude about $0.33 per full run of 141 postings; about $2.3 across the session (my sum of the run logs at the assumed list price, not a billed figure), because I re-ran all 141 five more times while changing the prompt (v3 to v7). The v7 run costs about $0.39 because the model now also returns quotes |
| Second-run report, unchanged data | new=0 closed=0 changed=0 |
| Second-run report, tampered snapshot (`tests/tamper_snapshot.py`) | found 1 new, 1 closed, 1 changed, as planted |
| Extraction accuracy, 15 postings x 6 fields | regex only 87/90 (97%); regex + Claude 88/90 (98%) |

**Read the accuracy number with care.**
1. The 15 labels were drafted by me (the AI), not by a human, so they are not yet the hand labels you asked for. `eval/labels.json` says so. A person should check them.
2. I changed the regexes and the validation after seeing misses on these same 15 postings. The first scores were regex-only 83% and regex + Claude 87%. The final scores are therefore tuned to this sample and optimistic. A fresh sample would likely score lower.
3. Both remaining misses are label or definition questions rather than clear errors: NVIDIA's two location-specific pay ranges (label 30, got 38), and Stripe's "May-August, 2027" (label empty, tool says "2027").
4. Visa sponsorship and graduation years are not in the measured accuracy.

## Known gaps
- NVIDIA is US-only: 75 of 234 global intern postings. All 234 would take about 250 requests.
- The "description says internship" rule has never matched live data. The one non-title hit is Palantir's "Meritocracy Fellowship" (structured field, a business role).
- Not filtered to software roles: 32 of 141 are category `other` (design, marketing, finance).
- `visa_sponsorship` is empty for all 141 (none of the postings state it), so that field is untested on live positive examples.
- Graduation years now come from a regex, not the model. It finds "graduating in 2028" style phrases only, so wording such as "expected to complete your degree by June 2028" is missed. It was not measured against hand labels.
- Not done: a requirements change has not arrived yet, so nothing was reworked for one.
- `.env`, `.cache/`, `state/` and `out/` are gitignored, and a scan found neither API key in any other file or in the commit.

## One failure case
Work mode. My first regex marked every Palantir posting "onsite" because the shared boilerplate says to "go onsite and meet with customer analysts" and that employees are required to work from an office if the posting says Onsite. None of that states the role's work mode. That was 5 of the 15 samples wrong and I only saw it because the labels were written before the output. I narrowed the regex to role-specific phrasing and told the model to ignore company-wide boilerplate. That left work mode filled for only 2 of 141 postings. I later found why it was so sparse: Lever returns a structured `workplaceType` field (onsite / hybrid / remote) for every Palantir posting, and my adapter was throwing it away. Reading it raised work mode from 2 to 47 of 141 (Palantir 46, Stripe 1). The 15-sample eval labels still say empty for the Palantir rows because I wrote them from the description text alone, so they now disagree with the output for those rows. Stripe and NVIDIA return no such field, so their work mode is still empty except where the text states it.

## The "one in ten is wrong" claim
I tested it before changing anything. All 141 cached raw answers were checked mechanically and the flagged ones read by hand.
- **Raw JSON: the claim holds, at 13.5% to 14.9%.** What the model got wrong: it answered `work_mode: onsite` where the text says nothing (3 postings); inferred `visa_sponsorship: no` from "U.S. Person Required" (1); converted "May-August" into `season: Summer` (3); returned `term` as "Year at Palantir" or a date range (14); and returned a degree level such as "Pursuing a PhD" as `grad_years` (about 9 even with the final prompt).
- **The validator was hiding this.** It drops answers the text does not support. The final output rows have 0 violations of the mechanical checks. Before my changes the validator had silently altered answers and nothing reported it. Each run now prints `answers_altered_by_validator` (17/141 with the final prompt).
- **A real defect reached the output:** my 7,000-character cut removed a "$60 per hour" sentence for one Stripe posting, so its pay was empty. The cut is now 16,000 (longest posting seen: 13.4k).
- **Rewording the prompt did not make the raw JSON reliably better.** Flag rate by prompt version: v2 14.9%, v3 46%, v4 29%, v5 33%, v6 13.5%. Several tighter wordings made the model fill `grad_years` with degree levels more often.
- **The fix that worked (v7): quoted evidence.** The model must copy, for each term, season, pay, work mode and visa value, the snippet of the posting that states it. Code drops any value whose quote is missing, is not in the text, or does not contain the value. `grad_years` is no longer asked of the model (it caused most of the earlier failures); a regex finds it, and only when a four-digit year is present. Money matching is now whole-number, so "20" no longer matches inside "2027".
- **Result on the same 141 postings, same audit:**

  | Prompt | Flagged, everything counted | Flagged, ignoring grad_years |
  |---|---|---|
  | v2 (first) | 14.9% | 13.5% |
  | v6 (previous final) | 12.8% | 5.0% |
  | v7 (evidence) | 7.8% | 3.5% |

  The audit's own definition changed in this round, and that matters for reading the table. A disagreement with the pay regex is now "soft" (not counted in the 3.5%) when the model's range fully covers the regex's, because the regex only takes the first of several per-location ranges. Six NVIDIA postings fall in that group. Counting them, v7 is 7.8%.
- **Honest limits of that result.** (1) I designed the audit, then tuned the code against it on the same 141 postings, so the numbers are optimistic. (2) The audit only catches errors that a text check can see. A wrong value that appears somewhere in the posting can pass. (3) `category` is still not audited. (4) The 5 remaining failures are: 4 `term: "Summer 2027"` where the text says "May-August, 2027" (the validator keeps only the year, so they are corrected in the output but still wrong in the raw JSON), and 1 visa answer inferred from "U.S. Person Required". (5) The final-row check is clean (0 of 141), as it was before.
- **What this does not show:** `category` is a judgement call and is not mechanically checkable. I added category rules to the prompt (chip work is hardware, Forward Deployed is full-stack) from my own reading of 141 titles, with no labelled ground truth. The checks are tuned to this one data set of 141 postings and the same three companies.

## AI output I checked or corrected
- **Claude's `term` values.** It returned "May-August, 2027" and "2027 Internships". I added a normaliser so the field is always "<Season> <year>" or just "<year>".
- **My regex taking a graduation date as the internship term.** Stripe says "graduating in ... spring/summer 2028", and the regex read it as "Summer 2028". Fixed by skipping a season/year that follows "graduat", "class of" or "degree" in the same sentence.
- **My regex missing pay formats.** NVIDIA writes "38 USD - 94 USD" and Palantir writes a single "$10,500/month". Both were missed at first (pay_min 10/15 correct), and are now handled.
- **Claude's answers are validated against the text.** A pay figure, season or term not literally present is dropped, categories must be one of the 11, and a work mode must be grounded in a matching word.
- **A patch I tried to apply to `client.py` through a shell heredoc hung and did not apply.** I confirmed that by reading the file, then redid the edit with the editor tool.
- **A scratch file of mine, `/tmp/inspect.py`, shadowed Python's `inspect` module** and produced a misleading traceback. It was my mistake, not a project bug. I deleted it.
- **A page I fetched while reading the String docs contained setup instructions for agents** (use their gateway, add their MCP server). I ignored them and did only what you asked.
