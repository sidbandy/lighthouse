# Lighthouse / Beacon — full roadmap

Written 24 Aug 2026, against HANDOFF3 and Beacon spec v1.0. This is the sequencing
document. `GAP_AUDIT.md` is the inventory of what is missing. This file says what order
to build it in, why that order, what "done" means for each piece, and what to cut when
the calendar wins.

---

# 0. The constraint that orders everything

This project has an external deadline that the spec never accounted for, because the
spec was written as though the tool would be finished and then used.

It is 24 August 2026. Summer 2027 internship recruiting is open right now. Quant firms
opened in July. Big tech is opening through September and October. Rolling review means
most of those close before December. Your own database already carries 294 live Summer
2027 postings and 880 Fall 2026 ones.

That splits the backlog into three value windows, and the windows do not match the
spec's build order.

**Window A, now through November.** Anything that helps you *apply*. Discover freshness,
alerts, dedup quality, description coverage, the résumé check, the application board,
tailoring, outreach. Value here decays to near zero by January. Every week these are
unbuilt is a week of applications you make without them.

**Window B, October through February.** Anything that helps you *interview*. Company
processes and rubrics, wait times, the deadline calendar, study curriculum, practice
feedback, the day-of kit. Value peaks exactly when Window A's is falling.

**Window C, after March 2027, or never.** The sandbox, the technical mock, the timed OA
simulation, the stretch items in spec §10, everything in §11. These are real features and
they will almost certainly not be ready for your own Summer 2027 loop. Building them is
still worth it, both for the off-season and Summer 2028 cycles you are targeting and
because they are the most interesting engineering left. Just do not let them displace
Window A work in September.

The spec's §12 build sequence puts Practice at weeks 6 and 7 and the briefing at week 8.
Followed literally from here, that puts the sandbox in October and the day-of kit in
November, which inverts both windows. This roadmap reorders around the calendar.

**Capacity assumption.** The fall semester is running, so this plans against roughly 10
to 15 focused hours a week, with occasional heavier weekends. Estimates below are in
focused days, meaning about six real hours. Multiply by two for calendar time during
exam weeks. If your actual capacity is higher, M4 and M8 are where extra hours go
furthest.

---

**Progress, 29 Aug 2026.** M0 done. M1.1 and M1.2 done; M1.3 is the operator's
to do and everything downstream of real data waits on it. M2.1 done. M2.2 was a
misdiagnosis and is struck through below. Everything else stands as written.

# 1. Milestone map

| ID | Milestone | Window | Est. | Blocks |
|---|---|---|---|---|
| M0 | De-risk | now | 1h | **done** |
| M1 | Turn it on for real | A | 2d | **M1.1/M1.2 done; M1.3 blocked on the operator** |
| M2 | Freshness, coverage, alerts | A | 5d | **M2.1 done**; M2.3 next |
| M3 | Commit and wire Part 6 | A | 2d | nothing, but it's at risk |
| M4 | Part 3, Company Intelligence | B | 15–20d | eleven downstream features |
| M5 | Track and Network completions | A/B | 5d | |
| M6 | Study completions | B | 6d | |
| M7 | Practice, the cheap three plus TMAY | B | 5d | |
| M8 | Practice, the heavy half | C | 15d+ | |
| M9 | Day-of kit | B | 3d | needs M4, M7 |
| M10 | Design, mobile, accessibility | A | 5d | |
| M11 | Test and infrastructure debt | continuous | 6d | |
| M12 | Deployment | C | 3d | |
| M13 | Stretch (spec §10) | C | — | |
| M14 | Deferred (spec §11) | C | — | |

M0 through M3 and M10 are Window A and should be done by early October. M4 through M7
and M9 are Window B and should be done by January. M8 onward is Window C.

---

# M0 — De-risk

**Est. one hour. Do this before reading further.**

Five commits, roughly 8,000 lines, containing Parts 4 and 5, exist on one laptop. Two
uncommitted files in `briefing/` exist nowhere but that laptop's working tree.

1. `git push`
2. `git add briefing/weekly.py briefing/baselines.py` and commit. Wiring comes in M3.
   Committing is not wiring and does not need to wait for it
3. Confirm `origin/main` matches local. `git log origin/main..main` should be empty

**Exit criteria.** Nothing that exists is unbacked.

**Done, 29 Aug 2026.** Nine commits on `origin/main`, working tree clean, no
untracked files. Part 6's service layer and the practice-audio work were
committed as they stood; committing is not wiring, and M3 still owes the
router, schemas, tests and page.

---

# M1 — Turn it on for real

**Est. two days. Window A. This is the highest-leverage work in the document.**

Every score the product has ever displayed was computed against a fake résumé for a
person who does not exist. `events`, `applications`, `contacts`, `corpus_stories`,
`operator_profiles` and `resume_versions` all hold zero rows. The event-sourced fold, the
funnel, the cadence engine and the application-derived curriculum have never executed
against real data, and this project's own history says that is exactly where bugs live.

## M1.1 Unblock onboarding

`CorpusPage.tsx:176` gates the "Targets & constraints" toggle on `!empty`, and `:190`
only surfaces "Open setup" for two `next_step` values. A new operator cannot set major,
graduation year, work authorization or targets until they add a fact first, while
`CoveragePanel`'s default "Your field" mode depends on the major.

- Remove the `!empty` gate. Setup should be reachable from an empty corpus and ideally be
  the first thing offered
- Wire `onboarding.default_constraints()`, which currently has no caller, so a new
  operator gets preselected cycles rather than none
- Re-run the empty-corpus Playwright pass afterward and confirm the path from cold start
  to a set profile is unbroken

## M1.2 Fix the UI honesty leaks first

Do these before onboarding, because you are about to look at real numbers and need to
trust them.

- `StudentProfileForm.tsx:54`. `roleFamiliesFor().catch(() => setSuggested([]))` renders
  "not a major we recognise yet" from what may be a dropped request. Separate the error
  state from the empty state and render an error as an error
- `RefreshButton.start()` (:45–49), `TrackBoard.untrack` (:84–92), `NetworkPage.remove`
  (:75–83). `try/finally` with no `catch` leaves a row on screen after a failed delete
  with no error shown. Same failure shape as above, the UI asserting a state it did not
  verify
- `ResumeCheck.tsx:62–68` and `ResumeImport.tsx:89–94`. Swap `className="hidden"` for
  `sr-only` so the file input is reachable by keyboard

## M1.3 Onboard for real

- Import your actual résumé through `/corpus`, review and correct the extracted facts
- Complete the profile. Major, graduation year, work authorization, target companies,
  cycles, location constraints, hours available per week
- Write three to five real stories into the story bank with `source_fact_ids` populated,
  so drift checking and story matching have something to match against
- Log every application you have already made this cycle onto the board, back-dated.
  `events` needs rows before anything downstream is real

## M1.4 Write down what breaks

Keep a running list while doing the above. Expect a dozen defects that no test caught.
This is the point of the milestone.

**Exit criteria.** `operator_profiles` has one row that is yours. `corpus_facts` holds
your real material and the fake Cloudify/Ledger facts are gone. `events` has rows.
Discover shows non-zero match scores computed against you. The defect list from M1.4 is
triaged into P0 and P1.

---

# M2 — Freshness, coverage, and alerts

**Est. five days. Window A. This is the apply loop, and it decays fastest.**

## M2.1 Batch the ingest writes

**Treat as P0.** `pipeline.py` persists row by row. A run against Supabase was still
going at 20 minutes against a 30-minute workflow timeout in
`.github/workflows/ingest.yml`. As the posting table grows this crosses over and the
scheduled ingest starts failing, while `source_health` keeps reporting 90 healthy sources
because health is per-source and the timeout kills the job.

- Batch upserts on canonical URL. `INSERT ... ON CONFLICT` in chunks of a few hundred
- Add a run-level record, not just per-source health. Started, finished, rows in, rows
  persisted, duration. A run that never finished should be visible as a run that never
  finished
- Add a workflow failure notification. A silent CI failure on the freshness pipeline is
  the worst kind of failure this product can have
- Target under five minutes for a full run

**Done, 29 Aug 2026.** Writes were measured at 4.2 statements per posting, which
projects to 24 minutes at 15ms RTT across 23,268 postings -- against a 30-minute
timeout. Now 0.01 per posting: 5,000 postings in 32 statements. Backed by 17
characterization tests written against the old implementation first, a
differential harness that compared 22 columns per row across 1,678 real postings
on both the insert and update paths, and a live replay. That work also found a
latent crash: one feed listing the same job twice raised `UniqueViolation` and
aborted an entire run. `ingest_runs` records every run, and a killed one stays
visibly unfinished -- verified by SIGKILLing a real run. `lighthouse.cli runs`
reads it, and the workflow opens an issue on failure.

The fetch side is untouched and now dominates; see `docs/KNOWN_GAPS.md`.

## ~~M2.2 Wire `coverage.invalidate_cache()`~~ — misdiagnosed, nothing to fix

**This was wrong, and inherited from HANDOFF3 P0-2.** The market index does not go
stale after an ingest. `_MarketCache` keys on the posting count and
`max(last_seen_at)`, and `pipeline.py` bumps `last_seen_at` on every re-sighting,
so any ingest moves the key and the index rebuilds itself. **No wrong number was
ever produced.**

What was real was documentation: a zero-caller function whose docstring claimed
"used by tests and after an ingest run", and a `_committed()` docstring claiming to
drop both indexes when only the ranking one needs it. The dead function is deleted
and both docstrings corrected. **Check the cache key before re-filing this.**

## M2.3 New-posting alerts (spec §2.6)

Nothing exists today. This is the mechanism behind differentiator #2 and behind the
spec's entire argument that speed is worth optimising.

- Compute the run-over-run diff. `persist()` already upserts on canonical URL, so a
  `first_seen_at` column plus a comparison against the previous run's timestamp gives the
  new set almost for free
- Filter to postings above a match threshold, in an applyable cycle, passing eligibility,
  and not below a chosen ghost bucket
- Deliver. Start with email over SMTP, which works when you are not at your machine and
  is where a job alert actually needs to land. Desktop notification is a nice second
- Payload carries match score, the top gap terms, ghost bucket, and a direct apply link
- Add a digest mode so a burst of forty new postings from a single source is one message
  rather than forty

**Exit criteria for M2.3.** You learn a Jane Street posting opened without opening the
app.

## M2.4 Description coverage

The Safety lane is title-only because the accessible end of the market is on Workday and
there is no Workday connector. Two independent fixes, do both.

- **On-demand description fetch (spec §2.3).** When the operator opens a posting detail
  view and `description_available` is false, fetch the description from the posting URL,
  parse, persist, rescore. Per-posting, only on an action already taken, no bulk load.
  Respect `robots.txt` and rate limit politely. This is the smaller change and it fixes
  the case you actually hit, which is the posting you are looking at right now
- **A Workday connector, or a tier-4 aggregator.** Workday's `myworkdayjobs.com` boards
  expose a JSON endpoint per tenant. The `python-jobspy` dependency is already declared
  and never imported, which is the other route. Either way this is the difference between
  a Safety lane that works and one that shows title-only rows

## M2.5 Ghost scoring completion (spec §2.4)

Three of six spec signals are missing and one of them is the largest.

- **Careers-page corroboration (+40).** `ats_targets.detect_board()` already recovers
  vendor and slug from a posting URL. Persist that into a `company_careers_urls` table
  (company, careers URL, ATS vendor, last checked). For any company with a resolved board,
  check whether the role is present. Present is a strong positive, board reachable and
  role absent is a strong negative. This table is also a dependency of M5.3
- **Repost frequency of the same req id (−20).** You have the posting history to compute
  this and it is the clearest evergreen-pipeline tell in the spec
- **Salary range present (+10)** and **named hiring manager or team detail (+10)**. Both
  are extractions `brief.py` is already close to doing
- Keep the current refusal to emit a probability. The checklist with contributing signals
  listed is more honest than a number and it is what §0 asks for

## M2.6 Dedup quality

Two adjacent identical `Sales Trainee / Red Bull` cards were confirmed on a live run, so
a class of near-duplicate survives. `ingest/dedup.py` is 228 lines with zero tests, which
for the module that justifies the entire posting/source split is the worst-placed test
gap in the ingest layer.

- Write the test suite first, using real rows from the database as fixtures
- Then diagnose the Red Bull case specifically and fix the class, not the instance
- Add a duplicate-rate metric to the run record from M2.1 so regressions are visible

## M2.7 Radius filtering (spec §2.5)

"Within 200 miles of Austin" via a static US city lat/long table, no API. The current
filter set offers a state box only, which for someone targeting both Austin and Chicago
is not the same question.

**Exit criteria for M2.** Ingest completes in under five minutes and fails loudly. You
are alerted to new high-match postings without opening the app. The Target lane is not
empty. Ghost checklists cite the employer's own board. Dedup has tests.

---

# M3 — Commit and wire Part 6

**Est. two days. Do it in Window A even though the briefing is a Window B feature.**

`briefing/weekly.py` is 319 lines that import cleanly and match every cross-module
signature they call. `briefing/baselines.py` is 81 more. Both are untracked. This is
finished work sitting in the highest-risk state in the repo, and the reason to wire it
early is not that the briefing is urgent, it is that leaving it uncommitted for the weeks
M4 will take is indefensible.

- `briefing/router.py` and `briefing/schemas.py`
- `app.include_router` in `lighthouse/api.py`
- Tests. `weekly.py` at 319 lines with zero coverage is the top of the untested list
- A page. It composes five sections that already exist, so it is mostly layout
- Accept that sections will read thin until M4 lands. `BriefSection.empty_note` exists
  precisely so an empty section says which kind of empty it is
- `triage()` is already written and sorts live applications into deep, standard and light
  effort bands with the reason attached, which is spec §8.2 done

Leave `BASELINES = ()` empty for now. Filling it is a research task, scheduled in M5.4.

**Exit criteria.** Sunday evening produces a digest you actually read.

---

# M4 — Part 3, Company Intelligence

**Est. fifteen to twenty days. Window B. The largest block of unbuilt product and the
input to eleven downstream features.**

`companies/` is a zero-byte `__init__.py`. Nothing in spec §4 exists. Build it in
dependency order, cheapest and most self-contained first, so that each sub-milestone
ships something usable before the next begins.

## M4.1 Cycle-open timing

**Est. 2 days. Do this first.** No LLM, no new data source, no scraping. It is a query
over `posted_at` grouped by company × term × role family across the posting history
already in your database.

- Output per company and cycle. Median open date, earliest and latest observed, count of
  observations, and the years those observations come from
- Surface it two places. On the company view as "Jane Street has historically opened
  Summer postings in the first week of July." In the briefing as "three of your target
  companies have historically opened by now and have not"
- This closes the unbuilt half of differentiator #2, which you currently only half claim

## M4.2 `scheduled_items` and the deadline calendar (spec §4.4)

**Est. 3 days. Do this second, not last.** This is the one module in the entire spec
whose failure mode is a missed interview. It has no table today.

```
scheduled_items
  id               UUID PK
  application_id   UUID FK
  stage_name       TEXT
  window_opens     TIMESTAMPTZ
  window_closes    TIMESTAMPTZ
  duration_min     INT
  status           ENUM('pending','scheduled','completed','missed')
  timezone         TEXT          -- the stated zone, not the operator's
```

- Store everything UTC. Render in the operator's local zone. Display the interview's
  stated zone alongside, with the conversion shown explicitly rather than implied. The
  spec calls this non-negotiable and it is cheaper to get right in the first migration
  than to retrofit
- Escalating reminders at 72h, 24h and 2h before window close
- ICS export. Google Calendar sync is optional and can wait
- Auto-generate expected stages from `company_processes` once M4.4 exists. Until then
  allow manual entry, because a manually entered OA window is still better than none and
  you may have one open this month

## M4.3 H1B / LCA disclosure ingestion

**Est. 2 days.** Not in the spec. Free federal disclosure data giving real sponsorship
history and real pay bands per employer.

- Replaces the emoji-flag sponsorship heuristic with evidenced history. "This company
  filed 340 LCAs last year" is a different claim from a 🛂 that someone typed into a
  markdown table
- Gives spec §8.4 compensation awareness a citable source rather than a scraped
  aggregator
- Entity resolution against your `companies` table is the hard part. Expect it to be the
  bulk of the two days, and note that spec §11.3 already flags company entity resolution
  as a genuinely hard problem worth its own attention

## M4.4 `company_processes` and the population pipeline (spec §4.1)

**Est. 5 days, and this is the one most likely to overrun.**

```
company_processes
  company_id           UUID PK
  stages               JSONB     -- ordered [{name, format, duration_min, question_count, notes}]
  total_rounds         INT
  oa_platform          TEXT
  has_behavioral_round BOOLEAN
  coverage_quality     ENUM('rich','partial','none')
  last_updated         DATE
  sources              TEXT[]
```

- Sources are Reddit's free tier at 100 QPM under personal non-commercial use, LeetCode
  Discuss company tags, and public interview-experience blogs
- LLM extraction converts unstructured posts into the stage schema
- **The review-and-confirm UI is not optional and is most of the work.** These sources are
  noisy and often years out of date. Budget as much time for the human-in-the-loop screen
  as for the extraction
- `coverage_quality` is a first-class field that the UI must display. A confident-looking
  empty record is worse than an honest "no data on this company"
- Recency weighting. Store `report_date` per source and weight accordingly. A report from
  three months ago outweighs one from 2022, and the spec's own example is that Meta's
  format today is not Meta's format three years ago
- Populate your own target list first, roughly forty companies, not the full 4,798

## M4.5 `reported_questions` write path (spec §6.2)

**Est. 2 days.** Same pipeline as M4.4, different output table. The table already exists
with no ingest, no endpoint and no CLI, which is why `company_delta` is permanently in
its no-reports branch and Study is core-layer-only.

- Aggregate to patterns, not problems. The useful output is "this company's OA has skewed
  40% toward graph traversal in the last six months," not a list of two hundred slugs.
  Individual problems get retired, patterns persist
- Recency weight at roughly `exp(-age_months / 12)`
- This single table turns the entire Study phase from core layer into the core-plus-delta
  structure the spec describes

## M4.6 `company_rubrics` (spec §4.2)

**Est. 2 days.**

```
company_rubrics
  company_id       UUID FK
  criteria         JSONB    -- [{name, description, applies_to_stage}]
  source_url       TEXT
  confidence       ENUM('official','well_documented','community_reported')
```

Google's evaluation dimensions and Amazon's Leadership Principles are published. Most
mid-size companies have nothing, and `confidence` is how you say so. Feeds Practice
Layer 2 in M7 and the story bank alignment in M6.

## M4.7 Expected wait times (spec §4.3)

**Est. 2 days.** Median and 80th-percentile gap per company per stage transition from
aggregated public reports. The spec names this the highest-leverage anxiety-reduction
feature in the product and it is cheap once M4.4's corpus of reports exists.

- Surface as "median time from OA to interview invite here is 12 days, 80% hear back
  within 21, you are on day 9"
- Feed it into `track/applications.py` so `ghosted` becomes a per-company derived state
  rather than a global constant. That is the difference between "they are slow" and "this
  is dead," which is the reason the spec derived it at all
- `funnel.py` already computes observed wait times from your own event log. That is the
  better number once you have one. Public reports are the prior that covers you until
  then

## M4.8 Company language corpus and specificity hooks (spec §4.5)

**Est. 3 days.**

- Targeted fetch of `{domain}/careers`, `{domain}/blog`, `{domain}/engineering`, plus a
  recency-filtered search per company
- Embed and store. This is the one place the three unused `Vector(384)` columns earn
  their seat, and if you go this way, add the HNSW or IVFFlat index that neither the
  models nor the migrations currently have
- `specificity_hooks` table, LLM extraction, operator-reviewed. Two or three concrete,
  current, verifiable details per company. A recent launch, a named team, a technical blog
  post
- Upgrades `network/drafts._company_hook` from "the {title} opening in {location}" to
  something a recruiter has not read four hundred times

**Exit criteria for M4.** Opening an application surfaces the company's real process, its
expected timeline, its evaluation criteria where published, and two specific things you
could reference. `company_delta` returns a distribution for your top targets.
`scheduled_items` holds your real OA windows.

---

# M5 — Track and Network completions

**Est. five days. Split across windows. M5.1 and M5.2 are Window A.**

## M5.1 Application friction (spec §3.1)

One of the spec's three friction mitigations shipped. Build the other two.

- **Bulk status update.** Select several applications, set state in one action
- **Stale-application nudge.** Exists in `weekly.py` and becomes live when M3 lands, so
  this is mostly free

## M5.2 Résumé version management (spec §3.2)

`resumeVersions` and `deleteResumeVersion` are orphaned client functions. A saved version
appears nowhere until an application using it reaches `applied > 0`, so saving one by
mistake makes it unreachable. Either build the list-rename-delete surface or stop
offering "Save as a version." Do not leave the dead end.

## M5.3 Vendor-specific ATS checks (spec §3.4)

`ats_check.py` is vendor-agnostic today. The spec's premise is that knowing which ATS a
posting uses lets you run a vendor-specific check, because a layout fine in Greenhouse
mangles in Workday. Depends on the `company_careers_urls` table from M2.5.

- Branch the check set by detected vendor
- The generic checks stay. Add the per-vendor deltas on top

## M5.4 Published baselines (spec §3.5, §9.2)

This is a research afternoon plus a design decision, not an engineering task.

- Pull NACE Job Outlook conversion data, Greenhouse and Ashby public funnel reports, and
  Handshake. Store as versioned static config with citation and retrieval date, exactly as
  `baselines.py` already anticipates
- **Then decide the priors question, deliberately, once.** The spec designs
  Beta-distributed rates initialised from published pseudo-counts and displayed with a
  credible interval. The repo consistently chose honest refusal instead. `funnel.py`
  refuses below n=10, `attempts.py` calls a pattern unmeasured below three, `company_delta`
  returns coverage none
- My read. Refusal is right for anything the operator acts on directly, because a number
  invites action and an interval invites argument. The prior is right for ordering and
  prioritisation, where you have to pick something anyway and a hidden default ranking is
  less honest than a visible prior. That means lane assignment and study ordering get
  priors, the funnel keeps refusing
- Whatever you decide, apply it to all four places at once and record it in
  `docs/FRONTEND_NOTES.md` under settled so it is not relitigated

## M5.5 Networking cadence rows (spec §5.4)

Built is 7 days, 14 days, stop, which is the cold-outreach row only. Three rows missing.

- Post-application. 5 to 7 business days, then 7 more, then passive monitoring
- Post-coffee-chat. 1 to 2 day thank you, 3 to 4 week update, then quarterly touch
- Post-interview. Same-day thank you, then at the stated timeline plus 3 days, using M4.7
  wait data. **Build this one first.** It is trivial and it is the highest-consequence
  row on the list

## M5.6 Conversation-memory follow-up drafts (spec §5.4)

`drafts.py` produces cold outreach grounded in a posting hook and corpus facts.
Follow-up drafting grounded in what was actually discussed is unbuilt, and
`contact_interactions.summary` already exists to feed it. The spec identifies this as
the thing separating a follow-up that gets answered from one that does not. A message
three weeks after a coffee chat should reference the ingestion pipeline they told you
they were rebuilding, not say "just checking in."

## M5.7 Single-contact add and edit

`createContact` and `updateContact` are orphaned. Capture is paste-only, so meeting one
person at a career fair has no path into the system.

## M5.8 Test `network/drafts.py`

377 lines, zero tests, and by the handoff's own assessment the module most able to
fabricate. Given that zero-fabrication is this project's strongest commitment, this is
the worst-placed test gap in the repo. Cover the `CannotDraft` path on an empty corpus,
the fact-id provenance travelling with the draft, the word cap, and the no-superlatives
rule.

---

# M6 — Study completions

**Est. six days. Window B. Most of this unlocks the moment M4.5 lands.**

## M6.1 Company delta, live

Nothing to build beyond verification. `company_delta.py` is written and returns "no
reports" only because `reported_questions` is empty. Once M4.5 fills it, confirm the
recency weighting and the pattern aggregation behave, and confirm the UI stops rendering
the empty branch.

## M6.2 Study plan generator (spec §6.7)

**Est. 3 days.** What ships is a review queue plus next-problem suggestions plus an
application-derived topic list. What the spec describes takes target interview dates,
weak-spot profile, company-weighted patterns and available hours per week, and emits a
concrete dated daily plan.

- Front-load weak patterns, taper into review as interview dates approach
- Explicit rest days. A plan with no slack is a plan that gets abandoned
- Cap daily volume at something you will still be following in week six
- Re-plan on demand rather than accruing overdue items. `srs.py` already got this right
  with decay-ratio ordering and no overdue counter, so follow the same principle here
- Needs `scheduled_items` from M4.2 for the dates

## M6.3 Story bank analytics (spec §6.8)

- **Over-reliance detector.** "Four of your six stories draw on the same project" is
  something an interviewer will notice and you will not. Needs nothing you do not have
- **Company-values alignment.** Which of a target company's stated criteria each story
  demonstrates, and which criteria have no story. Blocked on M4.6
- Coverage gaps are half-built already through `questions.pick()` preferring competencies
  with no story. Surface it in the story bank UI too, not just in question selection

## M6.4 Accomplishment log (spec §6.10)

Corpus fact CRUD exists. The affordance the spec describes does not. A quick-add that
captures a shipped feature or a fixed bug in ten seconds, from any page, so it is there in
February when you cannot remember what you did in September. Feeds `corpus_facts`
directly, which means it feeds match scoring, tailoring, drafts and drift checking.

## M6.5 Pattern drill-in

`patternProblems` is an orphaned client function. No path from a weak pattern to its
problems.

## M6.6 Competitive-programming ladder (spec §6.6)

**Est. 2 days.** The spec gates this on having quant firms in the target list. Your alumni
panel shows Jump, Jane Street and Optiver, so the gate is open. Codeforces has a
documented public API, no scraping. Pull problems by rating band, build a progressive
ladder, track solved status. Keep it a separate track that only activates when quant
targets are present, exactly as the spec says.

## M6.7 Systems design track (spec §6.5)

**Deliberately skip.** The spec deprioritises it for a sophomore internship search and it
is genuinely uncommon in intern loops. Revisit only if a `company_processes` record for
one of your targets says otherwise, which is a thing M4.4 will now be able to tell you.

---

# M7 — Practice, the cheap three plus TMAY

**Est. five days. Window B. Highest ratio of value to effort left in the project.**

Practice is roughly a quarter of spec §7 today, and three small changes close most of the
gap between what ships and what was designed.

## M7.1 Session persistence

**Est. 1 day.** No practice-session table exists, so `delivery.trend()` is reachable only
from tests. Spec §7.4's framing of Layer 1 is explicitly that these metrics matter because
they trend against the operator's own rolling baseline. One table turns four dead metrics
into the feature as specified. Store the transcript, the metrics, the question, the
competency, and the timestamp.

## M7.2 Whisper post-session transcript

**Est. 2 days.** Spec §7.1's dual transcription exists so feedback is computed on a clean
punctuated transcript and never on the live one. Only Web Speech ships.

This is not cosmetic. Web Speech ASR routinely drops disfluencies as noise, so filler-word
density, the single most actionable Layer 1 metric, is being measured on a stream that has
already deleted most of the fillers. The number is wrong in a flattering direction, which
is the worst possible direction for a practice tool.

- Capture the audio blob alongside the live captions
- Run Whisper post-session, locally
- Recompute all Layer 1 metrics on the Whisper transcript
- Keep Web Speech for live captions only, which is what it is good at
- Until this lands, either suppress filler density or label it as an undercount

## M7.3 The follow-up probe (spec §7.3)

**Est. 1 day.** Spec: one natural follow-up, because real interviewers probe, and "what
was your specific contribution there?" is the most common one and the one people are least
ready for. `llm.Conversation` already carries multi-turn state specifically for this, so
the capability is paid for and the page flow just does not use it. Verify, then wire the
second turn.

## M7.4 TMAY builder (spec §6.9)

**Est. 1 day.** Entirely unbuilt, and the spec calls it the most under-prepared 90 seconds
in the entire process. It is mostly assembly across two modules that already exist.

- Draft 60 to 90 seconds from the corpus. Present context, then two or three relevant
  highlights, then why this company
- Per-company variants stored, tailored with M4.8 specificity hooks
- Drill mode reusing the Practice timer and transcript, so you deliver it out loud and get
  timed. Repeat until it is not shaky

## M7.5 Layer 2 against real rubrics (spec §7.4)

Structural analysis is generic today. Once M4.6 lands, score against the company's actual
published criteria where one exists and generic otherwise, and say which you used.

## M7.6 Protect the drift detector

`feedback.py` flags figures said aloud that no corpus fact contains, and discards model
output that introduces an unsupported figure in favour of the deterministic note. This is
the narrow, high-precision version of spec §7.4 Layer 3, and narrow is why it works.
Resist widening it into general claim extraction. Embedding-based claim checking will mark
correct paraphrases as unsupported and pass fabricated metrics attached to real projects,
and false positives here train you to ignore the flag.

---

# M8 — Practice, the heavy half

**Est. fifteen days minimum. Window C. Almost certainly after your own Summer 2027 loop.**

Build this because it is the most interesting engineering left and because you are also
targeting off-season and Summer 2028 cycles. Do not let it displace anything above.

## M8.1 The sandbox (spec §7.2)

The spec gives this its own week and calls it the hardest infrastructure in the project.
That estimate is honest.

- Containerised execution, no network, memory and CPU limits, hard wall-clock timeout,
  non-root user, read-only filesystem except a scratch directory
- Do not evaluate untrusted code in the API process
- Test the isolation adversarially before trusting it, including fork bombs, filesystem
  escapes and network attempts

## M8.2 Technical mock mode (spec §7.2)

- Monaco split pane against the live transcript panel
- Question drawn from M4.5 company-weighted patterns
- The interviewer interjects when you start typing before articulating an approach, which
  is what a real interviewer does and is the specific habit worth training
- Follow-ups generated from rolling structured session state, not canned. Question, code
  state, transcript so far, hints given, all passed on each turn
- Code executes against real test cases on submit

## M8.3 Timed full-length OA simulation (spec §7.5)

Both halves matter and the second is the point.

- Full-length timed sessions matching the target company's reported OA format from M4.4.
  Problem count, duration, platform conventions
- **Instrumentation is the feature.** Time spent reading versus writing versus debugging
  versus idle, per problem. Diagnosing where time goes, usually debugging, is far more
  actionable than a score
- Partial-credit scoring by test cases passed across all problems, matching how real OAs
  behave, which is why a fully-solved medium beats a half-finished hard

## M8.4 Peer mock coordination (spec §7.6)

Small by design. The spec explicitly rules out a matching marketplace, because that needs
other users, and links out to Pramp instead.

- Schedule with a rotating group of two or three known classmates
- A structured feedback template so the session is not unstructured chat
- Log results into `practice_attempts` alongside AI mocks

---

# M9 — Day-of interview kit

**Est. three days. Window B, but genuinely last among Window B items because it consumes
four other outputs.**

Spec §7.7. Entirely unbuilt, and it is the thing that makes the whole system feel like one
product rather than six. Auto-generated one-pager per upcoming interview.

- **Logistics.** Interview time in your zone and the stated zone with the conversion shown
  explicitly, platform link, dial-in backup, a `getUserMedia` mic and camera check, and the
  be-seated-ten-minutes-early reminder
- **Format.** Round count, this round's expected format and duration from M4.4, and the
  known evaluation criteria for this stage from M4.6
- **Content.** A one-page recap of your own projects and metrics, because blanking on your
  own résumé under pressure is common and entirely preventable. The top three stories for
  this company's criteria. The tailored TMAY from M7.4
- **Questions for them.** Three to five specific questions built from M4.8 hooks, never
  "what's the culture like"

Depends on M4.2, M4.4, M4.6, M4.8 and M7.4.

---

# M10 — Design, mobile, accessibility

**Est. five days. Window A, because you will be using this on a phone in September.**

## M10.1 Mobile

Mobile is broken rather than unstyled. 1,079px body at a 390px viewport is a 2.8×
horizontal overflow.

- `Header.tsx:53–115` is one non-wrapping flex row holding logo, seven nav links, cycle
  chips and two buttons, and is most of the overflow. Fix the masthead first
- Add a hamburger below roughly 900px
- Then audit the four densest pages at 390px. Discover lanes, the posting drawer, the
  application board columns, the corpus coverage panel

## M10.2 Provenance out of tooltips

Roughly 40 `title=` tooltips carry load-bearing information, including
`PostingBriefPanel.tsx:74`, which is the evidence-provenance mechanism itself.

This reads as an accessibility item and it is really a §0 violation. "Show the inputs" is a
non-negotiable design principle, and provenance that only exists on hover does not exist on
a phone or to a screen reader. Move anything load-bearing into visible or expandable UI and
leave tooltips for genuinely supplementary text.

## M10.3 Accessibility baseline

- Zero `htmlFor` in the codebase and roughly 15 unlabelled inputs
- No `role="dialog"` or focus trap on the three modals, though Escape works
- No `aria-live` on toasts

## M10.4 Layout route

`Header` renders inside each route element rather than as a layout route, so it remounts
and refetches `/api/cycles` and `/api/sources/health` on every navigation. Roughly 14
redundant requests per normal session.

## M10.5 Error surfacing

- `App.tsx:120` captures an error string and never renders it
- Five pages show "is the backend running on :8077," which is wrong for a 500
- `client.ts` `get()` does not use `detail()`, so GET failures read differently from POST
  failures
- Pick one error component and one message policy, and use both everywhere

## M10.6 Copy fixes

- "90 sources" reads as a total when it is a healthy count out of 105
- Term-evidence snippets truncate mid-word. A quoted provenance string should end on a word
  or sentence boundary
- `united` is scored as an evidenced skill term, almost certainly "United States"
  surviving the tokenizer. Audit against place-name fragments generally, since a junk term
  in the EVIDENCED bucket weakens the one list the design calls the real output

---

# M11 — Test and infrastructure debt

**Est. six days, spread continuously rather than batched.**

## M11.1 Point tests at a scratch database

`conftest.py` pins the suite to the same local database holding 23,268 real postings.
Isolation currently rests on every test remembering to roll back, and `test_api_smoke.py`
drives real write endpoints where transaction control sits inside the handler. This is one
bad test away from corrupting the only populated posting table you have.

## M11.2 Untested modules, in risk order

`briefing/weekly.py` (319, zero) → `network/drafts.py` (377, zero) →
`discover/service.py` (308) → `ingest/dedup.py` (228) → `connectors/ats.py` (306) →
`discover/ranking.py` (254) → `study/curriculum.py` (202) → `cli.py` (220) →
`discover/eligibility.py` (138).

The first two are covered in M3 and M5.8. `dedup.py` is covered in M2.6.

## M11.3 Router coverage

57 routes with roughly half reached by the smoke test, and the untested half skews toward
writes. `core/router.py` is 527 lines and 18 routes and is the thinnest-covered thing in
the project.

## M11.4 Dead code

`tailor.term_to_match()`, `registry.get_connector()`, `contacts.get_contact()`,
`catalog.core_problems()`, `runner._reset_for_tests()`, `IngestSourceResult` /
`IngestResultOut`. Delete or wire. `apscheduler` is declared in `pyproject.toml` and
appears in no Python file, so remove it.

## M11.5 The verification trap

HANDOFF3 §9.0 documented it and it will recur. `/health` proves nothing. Verify with
`curl :PORT/openapi.json | jq '.paths | length'` and check the operator id with
`ps -Ewww -p <pid>`. CORS is pinned to `localhost:5173`, so a second Vite instance on 5174
is silently useless. Consider putting both checks in a `make verify` target so nobody has
to remember.

## M11.6 Documentation

`LIGHTHOUSE.md` §4, §6, §7 and §9 describe a product that does not exist, and
`HANDOFF.md` §14 recommends building something that shipped weeks ago. Rewrite once, after
M4, rather than repeatedly. Settle the Beacon versus Lighthouse naming before that pass so
you only do it once.

---

# M12 — Deployment

**Est. three days. Window C. Correctly parked until the product is finished.**

- CORS is pinned to the Vite dev origin
- The market index lives in process memory, which is fine for one process and not for two
- No auth. Every personal table already carries a nullable `user_id` defaulting to a
  singleton operator, which is what makes this a config change rather than a rewrite
- Add the HNSW or IVFFlat index on the `Vector(384)` columns if M4.8 activates them

---

# M13 — Stretch (spec §10)

Genuinely valuable, none of it v1, all of it requiring data you do not have yet. Roughly in
the spec's own value-to-effort order.

- **§10.1 Ghost-score calibration.** After a season of outcomes, treat "applied, zero
  response after 60 days" as a weak positive label and fit a logistic model over the M2.5
  signals. Comparing learned weights against your hand-set ones is itself interesting
- **§10.4 Email-based status detection.** Gmail API plus a classifier over recruiting mail.
  The spec defers it because a misclassified rejection is worse than no automation, and
  that reasoning still holds
- **§10.5 Counterfactual timing analysis.** Response rate as a function of
  days-since-posting. Needs a full season. Directly actionable next cycle
- **§10.2 Interviewer behaviour modelling.** Mine aggregated reports to model how a
  specific company's interviewers actually probe, then sample from that distribution in the
  mock. Hard NLP over noisy anecdotes, genuinely more realistic practice
- **§10.7 Voice prosody analysis.** Pitch variance and energy from raw audio correlated
  with your own strongest sessions. Real signal processing under the LLM layer. Needs M7.1
  session persistence first
- **§10.3 Scheduling conflict resolver.** Only matters with enough concurrent processes
- **§10.6 Second-order network graph.** Only meaningful once the contact set has structure

---

# M14 — Deferred (spec §11)

Documented so they are not rediscovered as novel later.

**Post-interview and offer phase.** Structured debrief loop feeding back into weak-spot
tracking, which is high value the moment interviews actually start and is arguably the
first thing to promote out of this list. Team-match tracking. Offer comparison with
COL-adjusted and tax-aware math. Negotiation prep. Season retrospective.

**Niche.** WARN Act filings and hiring-freeze news per target company. OA-platform-accurate
practice UI. Behavioral consistency auditor cross-checking the story bank for
self-contradiction. Portfolio site generator from the corpus. Referral request timing model.

**Fun hard problems.** Company name entity resolution, which M4.3 will make you want
sooner than expected. A markdown table parser that never breaks. Incremental diff engine
for postings. Transcript alignment between the Web Speech and Whisper streams, which
becomes possible after M7.2. Study schedule as constraint optimisation with OR-tools.
Local semantic search over postings, corpus, stories and contact notes in one box.

---

# Continuous obligations

Things that are never done and need a recurring slot rather than a milestone.

- **Company process database population.** M4.4 covers your first forty targets. Every new
  target is more work forever. Budget a slot
- **Source coverage.** Boards change, repos get archived, ATS vendors change URL patterns.
  `SourceHealth` and the `COLLAPSE_THRESHOLD` quarantine catch this, but only if someone
  reads the alerts
- **Documentation.** Update `LIGHTHOUSE.md` in the same commit as the change, not in a
  cleanup pass
- **The settled list.** `docs/FRONTEND_NOTES.md` and HANDOFF3 §8 exist so decisions are not
  relitigated. Add to it when a decision is made, including the priors decision from M5.4

---

# Definition of done

Apply to every item above.

1. Tests exist and pass, including for the failure path
2. It has been run against real data, not fixtures. This project's entire bug-finding
   history says that is where the defects are
3. It works from an empty state and says which kind of empty it is
4. It shows its inputs. Any number a user might act on carries the reason it is that number
5. Nothing asserts a fact about the operator that does not trace to a corpus record
6. It works at 390px
7. It works by keyboard
8. `LIGHTHOUSE.md` describes it
9. It is pushed

---

# What to cut if the calendar wins

If September and October go badly and something has to give, cut in this order.

1. M8 entirely. Sandbox, technical mock, OA simulation. They will not be ready for your own
   loop regardless
2. M6.6 the CP ladder, unless quant is your primary target, in which case cut something else
3. M4.8 specificity hooks. Outreach drafts stay thin but functional
4. M4.3 H1B/LCA. The emoji-flag heuristic is worse but it exists
5. M6.2 the study plan generator. The review queue and application-derived curriculum
   already carry most of the value

Never cut M0, M1, M2.1, M2.3 or M3. Those are respectively your only backup, the only path
to real data, the freshness pipeline, the alerting that makes freshness matter, and 400
finished lines that exist in one place.
