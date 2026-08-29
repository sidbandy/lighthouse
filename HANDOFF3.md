# Handoff 3 — Full project check-in

**Written 23 Aug 2026, from a complete read of the repository, the live database and
the test suite.** Nothing in this file is carried over on trust from an earlier
document; every number was re-measured. Where an existing doc disagrees, this file
says so explicitly and the older doc is wrong.

## Read this in this order

1. **This file** — where the project actually is.
2. `LIGHTHOUSE.md` — the vision, the rules, the design reasoning. **Its §4 status
   table and §7 tech section are stale** (see "Documentation drift" below). Read it
   for *why*, not for *what is built*.
3. `docs/KNOWN_GAPS.md` — the parking lot. Current and accurate.
4. `docs/FRONTEND_NOTES.md` — deferred design work, and a "settled" section that
   should not be relitigated.
5. `HANDOFF2.md` — the session-by-session decision record. Accurate through Part 5.
6. `HANDOFF.md` — **historical only.** Its §9/§10 predate Parts 4 and 5 and its §14
   "first moves" recommends building something that shipped weeks ago.

---

# 1. Where we are, in one page

Lighthouse is **five of six phases built, running, and green**. The engine is real:
23,268 deduplicated postings from 105 sources sit in the local database, 715 tests
pass in 11 seconds, and seven pages are wired end to end.

The gap between that and a finished product is not mostly code. It is three things:

**The product has never been used.** The world half of the database is fully
populated; the personal half is essentially empty. `events`, `applications`,
`contacts`, `corpus_stories`, `operator_profiles` and `resume_versions` all have
**zero rows**. The corpus holds 12 facts from a *fake test résumé*. So the
event-sourced application board, the funnel, the networking cadence and the
study curriculum have never once run against a real user's data — only against
synthetic fixtures in tests. Every score on screen today is computed against a
stranger's history.

**Part 3's Company Intelligence is the one real hole**, and it is load-bearing for
more than itself. `reported_questions` has no write path anywhere in the codebase,
so the study company-delta is permanently in its "no reports" branch. Networking's
draft hooks are thinner than designed. The Safety lane is populated from a
hand-maintained selectivity list. Three shipped features are running at partial
strength waiting on this one.

**Part 6 exists on disk and is invisible.** `briefing/weekly.py` (319 lines) and
`briefing/baselines.py` (81 lines) are written, correct against every signature they
call, and **untracked in git** — never committed, no router, no tests, no UI.

And one thing that is pure risk rather than product: **five commits are unpushed**,
including all of Parts 4 and 5.

---

# 2. Verified state

| | |
|---|---|
| Commits on `main` | 29 — **5 not pushed to `origin/main`** |
| Backend | 16,972 lines across 76 modules |
| Tests | **785 passing, 0 failing, ~4s** (re-measured 29 Aug 2026; was 715 on 23 Aug — the practice-audio work in the working tree added 70) |
| Frontend | 7,363 lines, 30 components, 7 routes |
| API | **57 routes** across 7 mounted routers |
| Database | Postgres 16.14 + pgvector 0.8.0, 15 tables, migration head `f4165aa75f37` applied |
| Lint | ruff clean; `tsc -b` clean; `npm run build` clean (29 Aug 2026) |
| Build | `web/dist` current — no source file is newer |

### The unpushed commits

```
4247558  Make it work for people who are not CS majors
5408edd  Part 5: study and practice
d8591f8  Part 4: networking, and the provider layer it needed
068f9f3  Fix what using the app cold actually exposes
524d1e6  Finish parts 1-3: tracked state, stories, résumé versions, routing
```

Roughly 8,000 lines — the two phases the vision calls "the prize" — exist only on
this laptop. `HANDOFF2.md` says "21 commits, all pushed", which was true when it was
written and has not been true since.

### Live local database

The shared half is real production-scale data. The personal half is empty.

| Table | Rows | |
|---|---:|---|
| `posting_sources` | 33,987 | ~1.46 sightings per posting — dedup is doing real work |
| `postings` | 23,268 | |
| `companies` | 4,798 | |
| `source_health` | 105 | |
| `corpus_facts` | **12** | the fake test résumé (Cloudify / Ledger / UT CS 2028) |
| `operator_targets` | 4 | |
| `practice_attempts` | 3 | |
| `events` | **0** | the event-sourced fold has never run on real data |
| `applications` | **0** | |
| `operator_profiles` | **0** | onboarding has never been completed |
| `contacts`, `contact_interactions` | **0** | |
| `corpus_stories`, `resume_versions` | **0** | |
| `reported_questions` | **0** | nothing can write to it — see §5 |

`.env` points at **Supabase**, not local. `backend/tests/conftest.py` pins the suite
to local Postgres regardless, which is what keeps it at 11 seconds instead of
running over the network against production.

---

# 3. The six parts, against the vision

`LIGHTHOUSE.md` §4 declares six phases plus a cross-cutting briefing. Here is the
real status. **Two rows contradict what that document says**, because it was written
on 7 Aug and Parts 4 and 5 landed on 11 Aug.

| # | Phase | LIGHTHOUSE.md says | Actually |
|---|---|---|---|
| 1 | Discover | Built | **Built** — and hardened by a cold-start pass |
| 2 | Track & Tailor | Built | **Built** — board, funnel, résumé versions, tailoring |
| 3 | Corpus + Company intelligence | Corpus built, intel not started | **Corpus built. Intelligence still not started** — the one real hole |
| 4 | Networking | *Not started* | **Built** — 9 modules, 10 routes, a page |
| 5 | Study & Practice | *Not started* | **Built** — 12 modules, 9 routes, two pages |
| 6 | Week-of / day-of | Not started | **Service layer written, uncommitted, unwired** |

### The seven differentiators (`LIGHTHOUSE.md` §2)

Six of seven are fully shipped. The seventh has a missing half.

1. **Every cycle, not just Summer** — shipped. Season resolver auto-advances; the
   term cascade records which rule fired.
2. **Apply in the first days** — *half shipped.* Twice-daily ingest works. "Knows
   when a company's cycle has historically opened" is **not built** — it needs the
   cycle-open timing query, which is Company Intelligence's first deliverable and
   needs no LLM and no new data source.
3. **One deduped list instead of nine tabs** — shipped, and measurably: 33,987
   sightings collapse to 23,268 postings.
4. **Don't waste applications on dead postings** — shipped. Ghost checklist, facts
   only, no probability.
5. **Reach a human** — shipped. The ATS parse preview is the strongest single
   feature in the product.
6. **Tailor with evidence** — shipped. Required vs preferred, knockouts, three
   honest buckets.
7. **Any major** — shipped in commit `4247558`. 15 role families, keyword-matched
   majors, and a coverage panel that measures against your own field.

### The rules (`LIGHTHOUSE.md` §3) — audit

Every one is being honored, and in several places the code is stricter than the rule
requires. This is the healthiest part of the project.

- **No invented numbers** — the funnel refuses a percentage below n=10;
  `company_delta` returns `coverage_quality: none` rather than a distribution;
  `attempts.py` substitutes the record for a mastery score; ghosting is a
  subtraction between two dates. `briefing/baselines.py` ships **deliberately
  empty** with a docstring arguing that a plausible uncitable baseline is worse
  than none.
- **Zero fabrication, both directions** — `llm.py`'s `verify_grounding()` pulls
  figures out of generated text and rejects any the declared sources don't contain;
  extraction and commitment are two separate API calls; `drafts.py` refuses outright
  on an empty corpus.
- **Show the inputs** — `term_rule` + `term_evidence` on every posting; every brief
  fact carries the sentence it came from; every draft carries its fact ids.
- **Honest over impressive** — thin evidence renders muted; an empty corpus renders
  an em dash rather than a confident zero.
- **Compliance is architectural** — paste-in capture from LinkedIn's own Alumni
  tool, nothing fetched; no auto-apply anywhere.
- **Students only** — internship *counts*, never years of experience.
- **Light theme only** — one `color-scheme: light`, no dark mode anywhere.

---

# 4. Everything that is built

## 4.1 Backend — 76 modules, 57 routes

### `core/` — the spine (13 modules)

Everything personal reads and writes through here.

- **`config.py`** — pydantic-settings with the `LIGHTHOUSE_` prefix, `.env` anchored
  to the repo root rather than CWD (so alembic run from `backend/` can't silently
  read a different file — that bug cost a session once). Rewrites bare
  `postgres://` to the psycopg driver, accepts Supabase's own env names as aliases.
- **`models.py`** — all 15 tables. Shared tables carry no `user_id`; personal tables
  carry a nullable one defaulting to a singleton operator. That split is what makes
  multi-user a config change rather than a rewrite.
- **`db.py`** — engine with `pool_pre_ping`, `session_scope()`, the `get_session()`
  dependency.
- **`events.py`** — the append-only log. `record()` separates `occurred_at` from
  `recorded_at`; `history_for_many()` batches a whole board into one query;
  `discard()` is the only deletion path and exists because untracking means "this
  was a mistake", not "this ended".
- **`corpus.py`** — fact and story CRUD, `corpus_documents()` flattening facts for
  matching, `_verify_fact_ids()` (what makes a story grounded), the fixed
  `COMPETENCIES` list, and `summarize()` → `is_usable_for_matching`.
- **`llm.py`** — the provider layer. `Conversation` carries multi-turn state because
  a behavioural mock has to remember what was said three minutes ago.
  `RuleBasedProvider` is the default and **raises if a caller supplied no fallback
  template** — with no key configured the deterministic path *is* the product, so a
  caller without a template is a caller that has not finished. `GeminiProvider`
  speaks plain HTTP. Any provider failure degrades rather than errors.
- **`textanalysis.py`** — the dependency-free tokenizer. Literal-token protection
  for `C++`/`.NET`, curated `TECH_TERMS`/`DOMAIN_TERMS`, multi-word phrases, a
  conservative stemmer with a `_NO_STEM` set and a `SYNONYMS` map (that map is what
  stops "Postgres" and "PostgreSQL" being reported as a false gap).
- **`majors.py`** — ordered keyword→role-family rules, most specific first so
  "computer engineering" beats "engineering". Returns `[]` for an unrecognised major
  rather than guessing.
- **`resume.py`** — PDF → draft facts. Section-header regex map, bullet heuristics,
  a line with ≥2 commas is body not a heading, `likely_image_based` flag under 100
  extracted characters.
- **`onboarding.py`** — profile and constraints upsert, `onboarding_state()`
  computing `next_step`.
- **`router.py`** — 18 routes. The largest router in the project. Also owns
  `_committed()`, which commits and then invalidates the match index so an edited
  corpus changes the next score.
- **`schemas.py`**, **`__init__.py`**.

### `ingest/` — the pipeline (16 modules)

- **`registry.py`** — the source catalogue. **13 connectors: 2 at tier 1, 11 at
  tier 2.** Tier 3 comes from `ats_targets` at runtime. Tiers 4 and 5 are documented
  in the docstring but **have no entries**.
- **`connectors/simplify.py`** — tier 1, Simplify's `listings.json`. Its multi-cycle
  `terms` array is what makes off-cycle coverage possible at all.
- **`connectors/markdown_repo.py`** — tier 2, curated GitHub tables. Carries company
  forward across `↳` rows; parses year-less dates like `Jul 09` by assuming a date
  cannot be in the future.
- **`connectors/ats.py`** — tier 3, Greenhouse / Ashby / Lever / SmartRecruiters.
  **The only tier carrying full descriptions.** SmartRecruiters needs a second call
  per job because its list response omits the description.
- **`table_parser.py`** — tolerant markdown parser: escaped pipes, `<details>`,
  `<br>`, HTML anchors, multi-value locations, closed/sponsorship/continuation
  markers. Never raises on a bad row; it counts them.
- **`normalize.py`** — the single home for cross-feed normalisation.
  `canonical_company` (accents, suffixes, initials, alias table), `canonical_url`
  (strips tracking params but preserves identity-bearing ones like `gh_jid`),
  location parsing, role-family and employment-type classification.
- **`dedup.py`** — block by canonical company, **veto any merge where ATS job ids
  differ**, then canonical URL, then fuzzy title. Picks longest company spelling,
  longest description, earliest `posted_at`, union of locations.
- **`terms.py`** — the ordered cascade: the feed said so → the title names it → the
  description states dates → a graduation requirement implies it. Records which rule
  fired and the quoting snippet. Returns `UNRESOLVED` rather than guessing.
- **`seasons.py`** — `Cycle`, `applyable_cycles(today)`, `normalize_year()`
  (`27`→2027). Nothing needs editing when the calendar rolls over.
- **`pipeline.py`** — per-source isolation, `SourceHealth` updates, a
  `COLLAPSE_THRESHOLD` quarantining any source returning under half its previous
  rows, `reconcile_companies()` re-keying stale canonical names, and `persist()`
  upserting on canonical URL.
- **`ats_targets.py`** — `SEED_TARGETS`, `detect_board()` recovering vendor+slug from
  a posting URL, `discover_targets()` prioritising operator targets.
- **`runner.py`**, **`base.py`**, **`router.py`** (3 routes).

### `discover/` — find what's worth applying to (11 modules)

- **`service.py`** — the SQL layer. `PostingFilters` compiles to a SQLAlchemy select
  across season/year, employment type, role family, sponsorship, US state, search,
  remote, description-only, applyable-only, posted-within-days.
- **`match.py`** — BM25 over a curated skill vocabulary against a `CorpusIndex`.
  The score is **coverage** — the weighted share of the posting's emphasised terms
  the corpus can evidence — not a normalised BM25 total. Produces the three buckets
  (evidenced / reword / gap), which are the real output; the number is secondary.
- **`ranking.py`** — caches the corpus index, scores a filtered page, builds the
  three-lane view with quotas and `has_more`.
- **`lanes.py`** — selectivity tiers, `assign_lane()` mapping match × selectivity to
  reach/target/safety **with a plain-English reason**, `WEEKLY_QUOTA`.
- **`coverage.py`** — the `MarketIndex` of term demand over a capped sample of
  described postings; per fact, which terms it contributes, how many postings it
  reaches, and how many it *uniquely* reaches.
- **`brief.py`** — compensation (hourly/monthly/annual normalised, with proration),
  GPA floor, duration, deadline, work pattern, named interview stages,
  responsibilities — each carrying its source sentence.
- **`ghost.py`** — age bands, corroboration count, last-seen freshness,
  posted-vs-updated mismatch, explicit closed flag, description presence. Derives a
  label. **No probability.**
- **`eligibility.py`** — graduation-window check. eligible / not eligible / **not
  stated**, and the last is never dressed up as either of the others.
- **`router.py`** (6 routes), **`schemas.py`**, **`__init__.py`**.

### `track/` — what happens after you decide to apply (8 modules)

- **`applications.py`** — the ordered `Stage` enum, the event→stage map, legal
  transitions, and `fold()` computing state from the log on every read.
  `Application` has no status column.
- **`funnel.py`** — conversions all measured from Applied (real pipelines skip
  stages), shown as "3 of 12 (25%)", refusing a percentage below `MIN_SAMPLE`=10.
  Wait times as observed medians with n and range.
- **`ats_check.py`** — the résumé feature. Clusters words into visual lines, locates
  a vertical gutter to detect columns, and builds the preview contrasting
  column-aware reading order against naive left-to-right. Then checks
  extractability, contact-in-header/footer, ligatures, risky bullets, non-ATS fonts,
  section headings, date formats, page length.
- **`tailor.py`** — splits a description into tiered blocks by heading, refines each
  sentence with inline required/preferred cues, extracts hard knockouts with the
  exact triggering phrase, buckets requirements, and adds "backable but missing from
  the résumé you sent" when `resume_text` is supplied. Strips EEO boilerplate first.
- **`resumes.py`** — version CRUD and `outcomes_by_version()`, counts only.
- **`router.py`** (10 routes), **`schemas.py`**, **`__init__.py`**.

### `network/` — Part 4 (9 modules)

- **`contacts.py`** — state folded from an interaction log, same shape as the board.
  Last outbound/inbound, unanswered outreach count, referral status, days silent.
- **`cadence.py`** — 7 days to the first chase, 14 to the second, then **stop**.
  Once exhausted it says so and produces nothing further rather than accruing a
  guilt counter.
- **`capture.py`** — parses a pasted LinkedIn Alumni block. Role-at-company pattern
  plus noise and location filters and a person-name heuristic. Nothing fetched.
- **`drafts.py`** — two variants where both specifics are *sourced*: the hook about
  them from a real posting on their company's board, the claim about the operator
  from corpus facts whose ids travel with the draft. `CannotDraft` on an empty
  corpus.
- **`alumni.py`** — the useful question is "which target companies do I know nobody
  at", because that is the list an hour of work can change.
- **`referrals.py`** — only `referral_confirmed` counts; an unanswered ask is the
  cold case wearing a hopeful label.
- **`router.py`** (10 routes), **`schemas.py`**, **`__init__.py`**.

### `study/` — Part 5a (7 modules)

- **`catalog.py`** — 14 patterns, 45 problems, 11 topics, every resource real and
  checked. **Config, not a table** — legible in a diff, correctable without a
  migration.
- **`curriculum.py`** — *the piece nothing else has.* Reads the postings on your own
  board, subtracts what your corpus evidences, and returns the topics your
  applications actually ask for, with the count attached and the exact words that
  triggered it.
- **`attempts.py`** — `PatternRecord` folding attempts into total / clean / recent
  window / days since / `is_weak` / `is_untouched`. Below three attempts a pattern is
  *unmeasured*, not weak. Surfaces prerequisite gaps.
- **`srs.py`** — SM-2, with everything interesting in what survives a missed week:
  no growing overdue counter, a hard daily cap, and ordering by **decay ratio**
  rather than by how overdue something is.
- **`company_delta.py`** — recency-weighted reported questions × your own record.
  Always returns "no reports" today; see §5.
- **`router.py`** (6 routes), **`__init__.py`**.

### `practice/` — Part 5b (5 modules)

- **`delivery.py`** — **never touches a model.** Filler density, words per minute,
  duration, longest silence — arithmetic over a transcript, so it works offline and
  is identical every run, which is what makes a trend mean anything.
- **`feedback.py`** — STAR structure detection from marker phrases, and **drift**:
  figures said aloud that no corpus fact contains. A model that introduces an
  unsupported figure has its output discarded for the deterministic note.
- **`questions.py`** — the bank, tagged with the same competency slugs the story
  bank uses; `pick()` prefers competencies you have no story for.
- **`router.py`** (3 routes), **`__init__.py`**.

### `briefing/` — Part 6, written but unwired (3 modules)

- **`weekly.py`** (319 lines, **untracked**) — `build()` assembles five sections:
  people to write to, applications gone quiet (≥14 days), study this week, stories
  to write, facts worth spreading out. Each `BriefSection` carries an `empty_note`
  so an empty section says *which kind* of empty it is. `triage()` sorts live
  applications into deep / standard / light effort bands by a legible rule that
  travels with its reason. Verified: it imports cleanly and every cross-module call
  matches a real signature.
- **`baselines.py`** (81 lines, **untracked**) — complete mechanism, deliberately
  zero data. `BASELINES = ()` with a docstring arguing the case. Named intended
  sources: NACE, Greenhouse and Ashby aggregate funnel reports, Handshake.
- **`__init__.py`** — committed in the very first commit, 0 bytes.

### `companies/` — Part 3, not started

One file, `__init__.py`, 0 bytes. A placeholder.

## 4.2 Frontend — 7 pages, 30 components

All routes are flat in `App.tsx`; every route element composes `<Header />` plus a
page. Every route has a nav entry and none is orphaned.

| Route | Page | What you do there |
|---|---|---|
| `/discover/:postingId?` | Discover (inline in App.tsx) | The daily surface. Filter bar, three lanes, posting cards. The optional param drives the centred posting window as an overlay, so it has its own URL and survives reload. |
| `/applications` | `TrackBoard` | Four stage columns, closed folded away, funnel on top, per-card dated timeline and back-dateable transitions. |
| `/network` | `NetworkPage` | Due-now queue, target companies where you know nobody, contact rows with interaction logging, draft modal. |
| `/study` | `StudyPage` | Prerequisite warnings, review queue with four outcome buttons, next problems, what your applications ask for, record by pattern. |
| `/practice` | `PracticePage` | Behavioural mock. Read-aloud, live captions via browser speech, timer, then delivery metrics, STAR chips, drift claims, matching stories. |
| `/corpus` | `CorpusPage` | Coverage panel, résumé import, fact list with per-fact reach, story bank, setup panel. |
| `/resume` | `ResumeCheck` | Drop a PDF, get the verdict, the parse preview, and severity-ranked findings. |

Supporting panels: `MatchMeter`, `TermChips`, `PostingBriefPanel`, `GhostChecklist`,
`TailorPanel`, `LaneColumn`, `PostingCard`, `FilterBar`, `SourcePanel`,
`RefreshButton`, `Header`, `FunnelPanel`, `CoveragePanel`, `FactList`, `FactEditor`,
`StoryBank`, `ResumeImport`, `SetupPanel`, `StudentProfileForm`, `ContactPaste`,
`DraftPanel`, `AtsFindings`, `ParsePreview`.

`api/client.ts` holds 51 functions over 43 paths. No state library, no React Query —
every page refetches on mount, mutations are `await api.x(); await load();`. One
poller: `RefreshButton` every 3 seconds.

---

# 5. What is not built

**Company & job intelligence (Part 3).** The main function of the phase, and none of
it exists. The `companies/` package is empty. This blocks more than itself:

- `reported_questions` has **no write path anywhere** — no ingest, no endpoint, no
  CLI. So `GET /api/study/companies/{id}/delta` is permanently in its "no reports"
  branch, and the study module's "core layer plus company delta" structure is
  currently core layer only.
- `drafts._company_hook` lifts "the {title} opening in {location}" from a posting.
  True and checkable, but thinner than a real specificity hook.
- The selectivity table is ~90 hand-maintained entries.
- Differentiator #2's second half — "knows when a company's cycle historically
  opens" — is unbuilt.

The sourcing is already researched and free: posting history already in the database
gives cycle-open timing with no new source and no LLM; US DOL H1B/LCA disclosure
data gives real sponsorship and pay bands; Reddit and LeetCode give interview
reports.

**Part 6.** Service layer written and uncommitted. Needs a router, schemas, tests,
`app.include_router`, and a page.

**Tiers 4 and 5 of ingestion.** Documented, no connectors. The `python-jobspy`
optional dependency is never imported. This matters because the genuinely accessible
end of the market is almost entirely on Workday, which has no connector — so the
Safety lane is populated from title-only rows.

**Auth and multi-user.** Deliberately deferred. Every personal table already carries
`user_id`.

**Semantic search.** The three `Vector(384)` columns are unused by design — a
reserved seat, not dead code.

---

# 6. The to-do list

## P0 — defects. Fix these on sight; they produce wrong numbers or block a user.

**Items 2–6 were fixed on 29 Aug 2026.** Item 1 still stands. Item 2 turned out to
be a misdiagnosis; what it was really pointing at is recorded below, because the
reasoning matters more than the fix.

1. **Push the five commits.** Parts 4 and 5 exist on one laptop. **Still open.**
2. ~~`discover/coverage.py:301` — `invalidate_cache()` has no caller.~~ **Fixed, but
   the diagnosis was wrong.** The claim was that the market index behind
   `/api/corpus/coverage` is never dropped after an ingest and goes stale. It does
   not: `_MarketCache`'s key includes the posting count and `max(last_seen_at)`, and
   `pipeline.py:253` bumps `last_seen_at` on every re-sighting, so any ingest moves
   the key and the index rebuilds itself. **No wrong number was ever produced.** The
   real defect was smaller and purely a documentation one — a zero-caller function
   whose docstring claimed "used by tests and after an ingest run", and a
   `_committed()` docstring in `core/router.py` claiming to drop both indexes when
   only the ranking one needs dropping. The dead function is deleted and both
   docstrings now describe what actually happens. **Check the cache key before
   re-filing this.**
3. ~~`SetupPanel` is unreachable on an empty corpus.~~ **Fixed.** The
   "Targets & constraints" toggle in `CorpusPage.tsx` is no longer gated on
   `!empty`. `SetupPanel` only ever needed `onboarding`, never the corpus, so a
   brand-new operator can now set major, graduation year and work authorization
   before adding their first fact — which is the order the coverage panel needs.
4. ~~`StudentProfileForm.tsx:54` renders a false claim on a network error.~~
   **Fixed.** A failed `roleFamiliesFor` now sets a separate `suggestFailed` flag
   and reads "Couldn't check this major just now", instead of asserting the major
   is unrecognised on the strength of a dropped request. The in-flight response is
   also now cancelled on change, so a slow reply for an old major cannot land as a
   claim about the new one.
5. ~~Unhandled promise rejections on three delete/mutate paths.~~ **Fixed.**
   `TrackBoard.untrack` and `NetworkPage.remove` now `catch` into `setError`, the
   same way the sibling `log()` in each file already did. `RefreshButton.start()`
   carried a second bug: on a failed start it left `wasRunning` set to `true`, so
   the next poll read as a run that had *finished* and refetched the lanes for a
   run that never began. It now resets the flag and surfaces "could not start".
6. ~~Keyboard users cannot upload a résumé.~~ **Fixed.** Both dropzones use
   `sr-only` instead of `hidden`, so the input keeps its place in the tab order,
   plus a `focus-within` ring on the label — without it the focused control is
   invisible to a sighted keyboard user, which is only half a fix.

## P1 — finish the product

7. **Company & job intelligence.** Start with cycle-open timing: a query over
   `posted_at` grouped by company × term × role family. No LLM, no new source, and
   it closes the missing half of differentiator #2. Then H1B/LCA for real sponsorship
   and pay bands. Then the reports pipeline, which is what finally fills
   `reported_questions` and turns `company_delta` from an honest empty state into
   the thesis sentence.
8. **Commit and wire Part 6.** Add `briefing/router.py` and schemas, mount it, write
   tests, build the page. The service layer is done; this is transport and UI.
9. **Replace the fake corpus and use the app for real.** Import a real résumé,
   complete onboarding, log real applications. Until `events` has rows, the board,
   funnel, cadence and curriculum have never been exercised against real data — and
   this project's entire bug-finding history says that is where the bugs are.
10. **Batch the ingest writes.** `pipeline.py` persists row by row. Against Supabase
    a run was still going at 20 minutes, and `.github/workflows/ingest.yml` has a
    30-minute timeout. **The scheduled ingest will likely time out as written.**
11. **A Workday connector, or tier-4 aggregators.** Without one the accessible end of
    the market has no descriptions and the Safety lane stays title-only.

## P2 — tests and hardening

12. **Untested surfaces, ranked by risk:** `briefing/weekly.py` (319 lines, zero) →
    `network/drafts.py` (377, zero — and it is the module most able to fabricate) →
    `discover/service.py` (308) → `ingest/dedup.py` (228 — surprising, given dedup is
    the point of the posting/source split) → `connectors/ats.py` (306) →
    `discover/ranking.py` (254) → `study/curriculum.py` (202) → `cli.py` (220) →
    `discover/eligibility.py` (138).
13. **Router coverage.** 57 routes; the smoke test reaches roughly half, and the
    untested half skews toward writes. `core/router.py` is 527 lines and 18 routes
    and is the thinnest-covered.
14. **Point the test suite at a scratch database.** `conftest.py` pins to the same
    local DB holding 23,268 real postings. Isolation currently rests on every test
    remembering to roll back, and `test_api_smoke.py` drives real write endpoints
    where transaction control sits inside the handler.

## P3 — polish, and the parking lot

15. **Consistent error surfacing.** `App.tsx:120` captures an error string and never
    renders it; five pages show only a generic "is the backend running on :8077",
    which is wrong for a 500. `client.ts` `get()` doesn't use `detail()`, so GET
    failures read differently from POST failures.
16. **Accessibility.** No `role="dialog"` or focus trap on the three modals (Escape
    works). Zero `htmlFor` in the codebase; ~15 unlabelled inputs. ~40 `title=`
    tooltips carry load-bearing information — `PostingBriefPanel.tsx:74`, the
    evidence-provenance mechanism, is tooltip-only. No `aria-live` on toasts.
17. **Mobile.** `Header.tsx:53–115` is a single non-wrapping flex row holding logo,
    seven nav links, cycle chips and two buttons. It breaks around 900px with no
    hamburger.
18. **Five client functions with no caller** — `resumeVersions`,
    `deleteResumeVersion`, `createContact`, `updateContact`, `patternProblems`. Each
    marks a missing feature: no résumé-version manager, no single-contact add or
    edit, no drill-in from a study pattern to its problems.
19. **Dead code to delete or wire:** `tailor.term_to_match()`,
    `registry.get_connector()`, `contacts.get_contact()`, `catalog.core_problems()`,
    `onboarding.default_constraints()` (nothing calls it, so a new operator gets no
    preselected cycles — arguably a small bug), `runner._reset_for_tests()`,
    `IngestSourceResult`/`IngestResultOut` in `discover/schemas.py`.
    `delivery.trend()` is reachable only from tests, and since practice sessions are
    never persisted the cross-session trend feature is unreachable from the API.
20. **`apscheduler` is an unused dependency.** Declared in `pyproject.toml` under
    `# Scheduling`; the string appears in no Python file. Scheduling is GitHub
    Actions plus an in-process thread. Remove it.
21. Everything in `docs/KNOWN_GAPS.md` and `docs/FRONTEND_NOTES.md` still stands.

## P4 — deployment, still correctly parked

CORS is pinned to the Vite dev origin. The market index is still in process memory.
Auth doesn't exist. None of it changes what the product does.

---

# 7. Documentation drift — fix this before the next session

This is worth its own section because it would actively mislead a fresh chat.

- **`LIGHTHOUSE.md` §4** lists Networking and Study/Practice as "Not started". Both
  shipped. **§6** describes them as future work in detail. **§7** says "LLM — not
  built yet; it is the next thing" (`core/llm.py` is 335 lines), says React 18
  (it's 19), says "no router yet" (react-router landed), says 467 tests (715) and
  ~10,500 backend lines (16,972). **§9** describes four pages; there are seven.
- **`HANDOFF.md` §14** tells a new session its recommended next build is the Track
  application board, which shipped in session 2.
- **`docs/KNOWN_GAPS.md`** "Models and database have drifted on three tables" is
  narrower than it reads. I diffed every `create_table`/`add_column` across all five
  migrations against `models.py`: **there is no column drift.** All 15 tables and
  every column match. The outstanding items are nullability defaults, one unique
  constraint expressed as an index, and a proposed `postings.role_family` index —
  real, but not structural drift.

One genuine schema observation neither doc mentions: **there is no HNSW or IVFFlat
index on any of the three `Vector(384)` columns**, in models or migrations. Moot
while embeddings are unused, but it belongs with that work if it ever happens.

---

# 8. Things not to relitigate

Recorded so nobody spends an afternoon reversing one.

- **Overlapping phrases are double-counted** on purpose. One pattern per phrase; a
  combined alternation would let the longest match swallow the shorter one.
- **`Vector(384)` is a reserved seat**, not dead code.
- **Conversions are measured from Applied**, not between consecutive stages.
- **Tier 3 is opt-in per company**, not a blanket crawl.
- **No authentication.** Single-user by design; `user_id` makes it a config change.
- **The board is not a draggable kanban.** You don't choose the stage — the employer
  does — so the interaction is "log what happened, on this date".
- **Reference data in `study/catalog.py` is config, not a table.**
- **The problem catalogue is deliberately 45 problems.** A list of four hundred is a
  list nobody starts.
- **An undefined Tailwind utility is silently dropped, not an error.** This has bitten
  twice (`mist-500` ×34, `font-600` ×49 — nothing in the app was bold for weeks).
  After any token change, grep `.ts` as well as `.tsx` and probe a computed style in
  the browser.
- **Bugs here are found by running against live data, not by reading code.** Every
  significant defect in this project's history was found that way.
- **Anything that breaks a feature is a bug, not a gap.** The parking lot is only for
  things that don't affect the app working.

---

# 9. Page-by-page technical design

**This section was written from a live run, not from reading code.** Both servers
were driven with Playwright at 1440×1000, every route visited, console output and
network traffic captured, and the whole thing repeated twice — once against an empty
corpus and once against the populated one.

## 9.0 How to reproduce this run, and a trap in doing so

Two uvicorn processes were already running on this machine, and **neither is what you
would guess**:

| Port | Started | Code | `LIGHTHOUSE_OPERATOR_ID` | Corpus it sees |
|---|---|---|---|---|
| 8078 | 7 Aug | **pre-Parts 4/5** | default | 12 facts |
| 8077 | 11 Aug | current | **`…0000000000c0`** | **0 facts** |

Both point at local Postgres. The `…00c0` override on :8077 is a deliberate
second operator used to exercise the cold-start path — it is *not* a bug, but it
means **the server the Vite dev origin talks to shows an empty corpus by default**,
and a session that doesn't check will conclude the corpus is broken.

Two lessons, both already in this project's history and both re-confirmed:

- HANDOFF2's near-miss ("a leftover uvicorn serving pre-change code, and
  `curl /health` answered `ok` the whole time") is still live. `/health` proves
  nothing. **Verify with `curl :PORT/openapi.json | jq '.paths | length'`** — current
  code serves 49 paths — **and check the operator id with `ps -Ewww -p <pid>`.**
- CORS is pinned to `localhost:5173`, so a second Vite instance on 5174/5175 is
  silently useless. Three were running.

For a clean run: `LIGHTHOUSE_DATABASE_URL=postgresql+psycopg://localhost/lighthouse
.venv/bin/uvicorn lighthouse.api:app --app-dir backend --port 8079`, then point
Playwright at 5173 and rewrite `:8077` → `:8079`.

## 9.1 Verification result

| Page | Console errors | Uncaught | Failed requests | HTTP ≥400 |
|---|---|---|---|---|
| Discover, Applications, Network, Study, Practice, Corpus, Résumé check | **0** | **0** | **0** | **0** |

Identical on both the empty and populated runs, and across the posting-drawer flow.
**The application is genuinely clean at runtime.** Deep-linking was confirmed
working live: clicking a card gives `/discover/13a2427e-…`, and a hard reload
restores the same URL with the drawer open.

The one structural failure found live: **at a 390px viewport the body is 1,079px
wide** — a 2.8× horizontal overflow. Mobile is not "untested", it is broken.

## 9.2 The shell — `Header.tsx`

Navy masthead, the only dark band on the page, rendered *inside each route element*
rather than as a layout route, so it unmounts and refetches `/api/cycles` and
`/api/sources/health` on **every navigation**.

Left to right: beacon mark and wordmark → seven `NavLink`s → live cycle chips
(**Discover only**) → "Refresh postings" (**Discover only**) → source health.

Live values: `Fall 2026 · 880`, `Winter 2027 · 32`, `Spring 2027 · 29`,
`Summer 2027 · 294`, `Fall 2027 · 6`, `Winter 2028 · 33`, `Spring 2028 · 2`,
`Summer 2028 · 5`. Eight chips is more than the design anticipated and the strip is
already `overflow-x-auto`.

"90 sources · 15 need attention" resolves correctly: `okSources` counts
`last_success_at && !is_quarantined` (90), `quarantined` counts
`is_quarantined || last_error` (15), and 90 + 15 = the 105 rows in `source_health`.
Not a discrepancy — but "90 sources" reads as a total when it is a *healthy* count.

**The whole masthead is one non-wrapping flex row** ([Header.tsx:53–115](web/src/components/Header.tsx#L53-L115)).
This is the single largest cause of the mobile overflow.

## 9.3 Discover — `/discover/:postingId?`

The daily surface, and the only page defined inline in `App.tsx` rather than in
`components/`.

**Row 1 — role families.** 14 plain-text filters, bold when selected.
**Row 2 — everything else.** Internship/New grad · Fall/Winter/Spring/Summer ·
Sponsors/No sponsorship/Citizens only · Remote · state box · posted 7d/14d/30d ·
Full descriptions · debounced search.

**The empty-corpus banner** (beacon-tinted, above the lanes) reads: *"Every score
below is 0 because your corpus is empty. That is not a judgement about these
postings — Lighthouse has nothing of yours to compare them against yet."* with a
"Set up your corpus" button. This is the zero-fabrication rule expressed as UI, and
it is one of the best things in the product.

**Three lanes.** Live with a real corpus: `Reach 20 of 118 · 3/week`, `Target 0 ·
6/week`, `Safety 2 · 2/week`. Each lane has a coloured full-width rule, a count, a
quota, and a one-line blurb. The empty Target lane says *"A posting needs a full
description before its match can be called realistic — try the 'Full descriptions'
filter"* — which is the honest reason, not "no results".

**A posting card**: title · company · match meter · up to 4 gap terms · hairline ·
metadata (term label + resolution rule, location, age, "N lists").

**Confirmed working as designed:** thin-evidence scoring. Several title-only cards
score `100` but render muted with `⚠ title only – weak evidence`, and sit **below** a
full-description posting scoring `19`. That is exactly the documented intent — the
number is not the primary output.

**Confirmed live from KNOWN_GAPS:** two adjacent identical `Sales Trainee / Red Bull`
cards. The gap entry is accurate and the visual effect is as bad as predicted.

### The posting window (drawer)

Centred overlay, its own URL, Escape closes, survives reload. Top to bottom:

1. Title, company, ✕
2. Chips — `Fall 2026` · `from description dates` · `Auckland, NZ` · `20 days ago`
3. **Term evidence, quoted**: *"closing date. Start Date: November 2026 WHAT TO EXP"*
4. Action row — `Open application ↗` (the only orange thing) · `Save` · `I applied` ·
   a back-dateable date input defaulting to today
5. **THE POSTING, IN FACTS** — `DEADLINE: Application Deadline: Friday, 28th August
   2026`, then `WHAT YOU'D ACTUALLY BE DOING` as 5 bullets lifted from the JD
6. **MATCH AGAINST YOUR CORPUS** — `19`, bar, `full description, 35 terms compared`,
   `6 terms evidenced, 1 to reword, 7 emphasised terms missing`, then three
   rule-marked buckets: EVIDENCED (software, engineering, testing, united, software
   engineering, Python) · PHRASE TO MIRROR (software development) · GAPS (aerospace
   ×3, C++, electrical, Linux, embedded, space ×15, launch ×9, production ×8, …)
7. `Tailor my résumé to this posting →`, then ghost checklist, sources, raw description

**Two small defects visible in that list**, both new:

- **The term-evidence snippet truncates mid-word** — `"…WHAT TO EXP"`. It is a quoted
  provenance string, so it should end at a word or sentence boundary.
- **`united` is scored as an evidenced skill term.** Almost certainly "United States"
  surviving the tokenizer. A junk term in the EVIDENCED bucket weakens the one list
  the design says is the real output.

## 9.4 Applications — `/applications`

`FunnelPanel` on top, then four columns (Saved / Applied / Assessment / Interviewing)
with closed folded behind a count. Cards expand to a dated timeline, a résumé-version
select, a notes textarea committing on blur, a date input and one button per legal
`next_event`.

Empty state, verbatim: *"Nothing tracked yet. Open a posting from Discover and save
it here. Once a few are logged, this page can tell you how long each company actually
takes to reply — from your own dates, not from averages someone else published."*
That names the next action and the payoff. `FunnelPanel` returns `null` at
`total === 0`, so the board's own empty state carries the page.

## 9.5 Network — `/network`

Intro nudge (*"Set your school on My corpus and Lighthouse can mark which contacts
are alumni"*) → `Add contacts` toggle → **DUE NOW** → **TARGET COMPANIES WHERE YOU
KNOW NOBODY** → contact list.

The alumni panel works with zero contacts and is the best thing on the page:
`Jump Trading 48 open · Jane Street 38 open · Optiver 22 open · Stripe 12 open`,
followed by the compliant capture instruction. This is real, useful output derived
from `operator_targets` × live postings with no personal data at all.

## 9.6 Study — `/study`

**DUE FOR REVIEW** → **PRACTISE NEXT** → topics from your applications → record by
pattern.

With three logged attempts it correctly shows *"Nothing to review yet… a missed week
costs nothing"* and suggests four easy entry problems — Contains Duplicate, Valid
Palindrome, Best Time to Buy and Sell Stock, Binary Search — each with the reason
attached (*"No attempts logged for arrays and hashing yet — start here"*) and four
outcome buttons. The reason-per-suggestion is the "show the inputs" rule holding.

**The application-derived curriculum — the piece nothing else has — renders nothing,
because `applications` has 0 rows.** The strongest idea in the phase is invisible
until the board is used.

## 9.7 Practice — `/practice`

Competency label (`OWNERSHIP`), the question, `▸ Read aloud`, `Start answering`.
After an answer: delivery metrics, STAR chips, drift claims, matching stories.
Fully config-driven, so it is the one page that works identically with an empty
database. `Start answering` is permanently disabled in browsers without
`webkitSpeechRecognition`; typing is the fallback.

## 9.8 My corpus — `/corpus`

The spine. Top to bottom: onboarding banner → `Targets & constraints` toggle →
**coverage** → résumé import → fact list → story bank.

Live coverage: *"Counted across 502 postings that carry a full description"*, `289 of
502 sampled postings mention at least one term you can evidence`, `213 mention
nothing your corpus covers`, with the caveat that a counted term *"is not a claim
that you'd be a strong candidate"*. Then the gap list with demand counts: `AI 222 ·
electrical 95 · C++ 93 · supply chain 82 · reliability 75 · autonomy 74 · …`, under
the heading *"These are real gaps, not keywords to add."*

**This is the cold-start trap in P0 #3.** On the populated run the banner says "Set
your constraints / Open setup" and setup is reachable. On the empty run it is not —
`{!empty && …}` at [CorpusPage.tsx:176](web/src/components/CorpusPage.tsx#L176) hides
the toggle, and the coverage panel's default "Your field" mode depends on a major the
user has no way to enter.

## 9.9 Résumé check — `/resume`

Single dropzone: *"Will your resume reach a human?"* → verdict card → `ParsePreview`
(laid-out vs ATS-extracted, side by side) → severity-ranked findings. Nothing is
stored; the file is written to a temp path, analysed, deleted. `Save as a version`
writes a `ResumeVersion` that the Applications board can attach to a row.

Keyboard users cannot reach the file input (P0 #6).

## 9.10 Is the flow connected?

Architecturally, yes — and the connections are the product's thesis:

```
Résumé PDF ─→ Corpus ─┬─→ Discover match scores ─→ drawer ─→ Save / I applied
                      │                                            │
                      ├─→ Tailor (per posting)                     ▼
                      ├─→ Network drafts (refuses if empty)   Applications ─→ Funnel
                      └─→ Practice drift + stories                 │
                                                                   ▼
Résumé check ─→ ResumeVersion ─→ Applications dropdown       Study curriculum
```

**Every arrow is implemented.** But three joins are currently dark, and all three are
data problems rather than code problems:

1. **Corpus → everything.** With an empty corpus, Discover scores are all 0, drafts
   refuse, tailoring has nothing to compare. And the one screen that fixes it is the
   one the empty state hides.
2. **Applications → Study curriculum.** `applications` has 0 rows, so the flagship
   "what should I study, based on where I applied" renders empty.
3. **Company intelligence → Study / Network / Lanes.** Never built.

There is also one genuine **dead end in the UI**: `Résumé check → Save as a version`
writes a row that appears nowhere until an application using it has `applied > 0`
([TrackBoard.tsx:147](web/src/components/TrackBoard.tsx#L147)). The
`resumeVersions` and `deleteResumeVersion` client functions exist with no caller, so
a saved version cannot be listed, renamed or deleted. Save one by mistake and it is
unreachable.

## 9.11 Added to the to-do list from this run

- **P1** — Mobile is broken, not merely unstyled: 1,079px body at a 390px viewport.
  Fix the masthead first; it is most of the overflow.
- **P2** — Term-evidence snippets truncate mid-word in the drawer.
- **P2** — `united` scored as an evidenced skill term; check the tokenizer against
  "United States" and similar place-name fragments.
- **P2** — Résumé versions have no management surface; wire the two orphaned client
  functions or stop offering "Save as a version".
- **P3** — `Header` remounts and refetches cycles + source health on every nav. A
  layout route would remove ~14 requests from a normal session.
- **P3** — "90 sources" reads as a total; it is a healthy count out of 105.

# 10. First moves in a new session

```bash
# verify a green baseline
.venv/bin/pytest backend/tests -q          # expect 715 passed, ~11s
.venv/bin/ruff check backend               # clean

# run it — note .env points at Supabase, so override for local work
LIGHTHOUSE_DATABASE_URL=postgresql+psycopg://localhost/lighthouse \
  .venv/bin/uvicorn lighthouse.api:app --app-dir backend --port 8077 --reload
cd web && npm run dev                      # :5173, expects the API on :8077

# CLI, no server needed
PYTHONPATH=backend .venv/bin/python -m lighthouse.cli sources
```

Then, in order:

1. `git push` — before anything else.
2. Fix the P0 list. It is six items and none is large.
3. Import a real résumé and complete onboarding, so the app is finally running
   against the operator's own data rather than a stranger's.
4. Commit `briefing/`, then wire it.
5. Start Company Intelligence with cycle-open timing.

And update `LIGHTHOUSE.md` §4, §6, §7 and §9 to describe the product that exists.
