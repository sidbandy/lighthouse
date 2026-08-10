# Handoff 2 — Session register

A record of what one working session accomplished. `HANDOFF.md` describes the
project as it stands; this file describes what changed and why, so the history
of decisions survives between chats.

**Convention going forward:** each session appends its own numbered section
here. Do not overwrite `HANDOFF.md` — update it, and log the session below.

---

# Session 2 — 30 Jul to 6 Aug 2026

## Where this session started

- 15 commits, all pushed. 376 tests passing, clean lint, app running.
- Built: the ingestion engine (~95 sources, 3 tiers, dedup, season-aware), the
  Discover three-lane view, the résumé ATS checker and per-posting tailoring.
- The corpus and onboarding existed as **service modules only** — no HTTP API,
  no UI. The corpus was populated by script, seeded with a fake test résumé.
- Dark slate theme. Local Postgres only. No deployment story.

## Where it ended

- **21 commits, all pushed.** 467 tests, clean lint, clean typecheck, clean
  production build.
- Four working pages: Discover, Applications, My corpus, Résumé check.
- Light "lighthouse" theme throughout.
- Supabase live with the full schema; scheduled ingestion via GitHub Actions.
- Four new docs: `KNOWN_GAPS.md`, `FRONTEND_NOTES.md`, `DEPLOYMENT.md`, and the
  non-technical overview at `~/Downloads/lighthouseOverview.doc`.

---

## What was built

### 1. The corpus page, and the API layer under it

The service modules existed; nothing exposed them. `api.py` mounted only
discover/ingest/track.

- **`core/router.py`** — facts CRUD, résumé extraction, coverage, onboarding
  state, targets, constraints, company search.
- Extraction and commitment are **two separate calls**: `/corpus/extract`
  returns drafts and saves nothing, `/corpus/facts/bulk` saves what was kept.
  The zero-fabrication rule expressed as an API rather than a convention.
- **Constraints had nowhere to live.** `OperatorConstraints` was an in-memory
  dataclass and `onboarding_state()` took it as a parameter no caller supplied,
  so `constraints_set` was permanently false and onboarding could never
  complete. It got a table.
- **`discover/coverage.py`** — the part that makes the page more than CRUD.
  Every fact reports the skill terms it contributes, how many ingested postings
  mention each, and how many postings **no other fact reaches**. On the seeded
  corpus this correctly showed standalone `Go`, `React` and `TypeScript` skill
  facts adding zero coverage the Cloudify and Ledger entries didn't already
  give.
- Corpus-wide gaps restricted to recognised skill vocabulary. Unfiltered, the
  top gaps were "engineer", "software", "technology", "problems".

### 2. Retheme — dark to lighthouse palette

Dark slate was a workspace, not Lighthouse. Now cream `paper`, white cards, one
`navy-*` ramp, `beacon-*` orange rationed to primary actions and live figures,
navy masthead with an orange hairline.

Token names changed too: `ink-*`/`mist-*` were dark-theme concepts (ink was the
darkest *background*, mist the brightest *text*), so swapping only hex values
would have left an inverted scale for every future reader. Nineteen components
swept against an explicit mapping table.

Design decisions, recorded in `FRONTEND_NOTES.md` as settled:
- Terms are flat with a coloured left rule, not pills — thirty rounded outlines
  read as decoration.
- Lane columns titled under a full-width rule in the lane colour.
- Filters plain text until selected.
- Card metadata below a hairline.

### 3. Track — the application board

- **`core/events.py`** — the append-only log. The `Event` model existed and
  nothing had ever written to it.
- **`track/applications.py`** — stage folded from events on every read.
  `Application` still has no status column.
- **`track/funnel.py`** — conversions from Applied, shown as "3 of 12 (25%)",
  refusing a percentage below `MIN_SAMPLE`=10. Wait times as observed medians
  with n and range; under n=3 it lists raw observations.
- Ghosting is a dated fact: "31 days since you applied, no response". Measured
  from the last **employer** signal, so your own note doesn't reset the clock.
  Silent on day zero.
- One-click save / "I applied" from the posting window.

### 4. Discover — the posting brief and refresh

- **`discover/brief.py`** — pay, working pattern, length, deadline, GPA floor,
  named interview stages, and what you'd actually be doing, each with its source
  sentence. Measured over 400 real descriptions: pay 30%, length 20%, pattern
  19%, process 10%, responsibilities 77%.
- Compensation took three passes against live data. Unit coverage went 40% →
  92% by taking the unit from anywhere in the sentence ("$25.00 USD Hourly",
  "the annual base salary is $120,000"). An unqualified figure under $1,000 with
  no rate unit is rejected, because "$2 increase in pay" is not a salary.
- Side drawer became a **centred window** — a reading surface meant to replace
  opening the job site in another tab.
- **`ingest/runner.py`** — background ingest with pollable status, and a refresh
  button showing elapsed seconds. Verified live: 13/13 sources, 36,221 raw →
  26,566 deduped, 1,690 new postings.

### 5. Student profile and eligibility

Audience narrowed to **students and new grads only** — decided this session, and
it shapes the product.

- Profile holds school, major, degree level, graduation term, internships
  completed. **Counts, never years of experience.**
- **`core/majors.py`** — major → role families, keyword-matched since majors are
  written a hundred ways. Generous (a CS major gets swe/ai_ml/data/security),
  and returns *nothing* for an unrecognised major rather than guessing.
- **`discover/eligibility.py`** — graduation window check. Eligible / not
  eligible / not stated, and the last is never dressed up as either of the
  others. Over 400 postings, 43 state a class year and **14 would knock out a
  2027 grad**.
- Profile form with live preview: typing "Finance" shows *Finance · Business ·
  Quant · Data* before you save.

### 6. Deployment groundwork

- Supabase live: project `svvwkhpobrpgjlgelfzr` (ca-central-1), Postgres 17,
  pgvector enabled, **all 14 tables migrated**, connection verified through the
  session pooler.
- **`.github/workflows/ingest.yml`** — scheduled ingest, twice daily. This is
  what removes the need for a paid always-on server: the background thread
  couldn't survive a host that freezes processes between requests.
- `docs/DEPLOYMENT.md` — Vercel + Supabase + Actions, all permanently free.
  Railway and Fly ruled out (trial credit, not standing free tier).
- Config accepts Supabase's own env names and rewrites a bare `postgresql://`
  scheme to the psycopg driver.

### 7. Code style pass

Fifteen module headers ran past twenty lines, some restating rationale twice,
several narrating bugs older versions had. Reduced to one to four lines.
Docstrings replaced by AST span so no logic could be touched.

---

## Bugs found and fixed

All found by running against live data. None by reading code.

| Bug | Consequence |
|---|---|
| `companies.tier` stored selectivity **and** "is a target" | Marking Jane Street a target demoted it from selectivity 4 to 2 and moved it out of Reach. Jump Trading was sitting in the Target lane. Split into a personal `operator_targets` table. |
| `mist-500`/`mist-600` used 34× but never defined | Undefined Tailwind utilities are silently dropped. Text meant to be quietest rendered at rgb(195,204,219) — *brighter* than the tier above it. |
| `font-600`/`font-700`/`font-500` used 49× but never defined | **Nothing in the app had ever actually been bold.** Only surfaced because `@apply` on an undefined class is a hard error, unlike its use in JSX. |
| `group-hover:text-white` on a card title | Title became invisible on hover against a white card. |
| `lib/format.ts` missed by the theme sweep | The sweep globbed `*.tsx` only; `scoreColor` kept returning a token that no longer existed. |
| Funnel stage counts used `>=` | An application that went straight from applied to interview counted as having reached an assessment it never had. |
| `FunnelReport.total` counted saved bookmarks | "Across 12 applications" above conversions all measured out of 6. |
| A rejection wasn't counted as a "first response" | Silently dropped the most common — and often only — reply from the time-to-response sample. |
| **Board stamped every stage as "now"** | Back-filling a real search would have logged twelve applications as all happening today, corrupting every wait-time figure. **This was wrongly filed as a gap first — see below.** |
| Synonyms scored as different skills | "Postgres" vs "PostgreSQL" — could report a gap the user doesn't have. A false gap breaks zero-fabrication from the other direction. |
| Alembic migration silently did nothing | Its template puts a docstring above `pass`; a patch matching only `pass` produced an empty revision that was **stamped as applied and reported success**. |
| `env_file=".env"` resolves against CWD | Running alembic from `backend/` used the local default and reported a successful no-op migration against the wrong database. |
| `DATABASE_CONNECTION_STRING` accepted as an alias | A `.env` holding only a hostname became the database URL. Broke 34 tests. |
| Test suite followed `.env` to Supabase | Every DB test ran over the network against production. 30 failed, suite went 1.2s → 15.6s. Pinned by `backend/tests/conftest.py`. |

### The triage rule this session established

Two defects were filed in `KNOWN_GAPS.md` that did not belong there — the
back-dating bug and the synonym bug. Both were pulled back out and fixed.

**The rule now, in both docs:** anything that breaks a feature is a bug, not a
gap. The parking lot is only for things that do not affect the app working. A
defect that records wrong data or produces a wrong number gets fixed on the
spot, however small it looks.

---

## Decisions made this session

| Decision | Rationale |
|---|---|
| Students and new grads only | Shapes the profile, the corpus, the résumé checker, eligibility. Industry professionals later, if ever. |
| Light theme only, lighthouse palette | No dark mode, ever. |
| Profile + major system before Supabase auth | Useful immediately; also the exact shape multi-user needs. |
| Email + password auth | Zero external setup. Google can be added later without a data-model change. |
| Local Postgres for dev, Supabase for deployment | Keeps the suite at ~2s and works offline. |
| Vercel + Supabase + GitHub Actions | Only combination that is permanently free with no card. |
| Functionality before frontend polish | Frontend ideas go to `FRONTEND_NOTES.md`. |
| Code must not read as machine-written | Drove the docstring pass. |

---

## Current state

**Repository:** 21 commits on `main`, all pushed to `sidbandy/lighthouse`.

**Verification at session end:** 467 tests passing (~2s), ruff clean, typecheck
clean, production build clean, migrations round-trip, all four views driven
through the real UI with no console errors.

**Local database:** 12 corpus facts (still the fake test résumé), 0
applications, 0 profiles, ~23k postings.

**Supabase:** schema applied, being populated.

**`.env`** points at Supabase. Tests are pinned to local by `conftest.py`
regardless. For local development, override `LIGHTHOUSE_DATABASE_URL`.

---

## What the next session should pick up

1. **Finish the stateless refactor.** The market index still builds in process
   memory (~1s). Precompute into a `posting_terms` table during ingest; let
   `coverage.py` read counts and reach as SQL. ~85k rows. **Required before the
   API goes serverless.**
2. **Supabase auth and multi-user.** Email + password. Every personal table
   already carries `user_id`; the work is an auth dependency resolving the
   request's user instead of the singleton, plus signup/login UI.
3. **Show tracked state on postings.** The drawer offers "Save"/"I applied" even
   for something already on the board. One join. Highest-value UX item left.
4. Then Company Intelligence, which needs the Gemini provider layer.

## Outstanding items requiring the operator

- **GitHub Actions secret.** Repository → Settings → Secrets and variables →
  Actions → New repository secret, named `LIGHTHOUSE_DATABASE_URL`, value = the
  same session-pooler connection string as `.env`. The scheduled ingest cannot
  run without it.
- **Replace the fake corpus.** `corpus_facts` still holds 12 facts from a test
  résumé. Import a real one on the My corpus page; every match score until then
  is computed against a stranger.

---

# Session 3 — 7 Aug 2026

## Where this session started

22 commits pushed, 467 tests, four working pages. The queued next steps were
three deployment items and one feature.

## What changed, and why

The session opened with an audit against the original spec rather than with
code. Two things it found reset the plan:

- **`LIGHTHOUSE_SPEC.md` did not exist** — not in the repo, not anywhere in git
  history — despite `HANDOFF.md` citing it as the source of truth. Every session
  since had been working from the build plan, which is a *derived* document.
- **The build plan had silently dropped Networking.** Its §12 defers "the
  networking/outreach module (spec §5)"; the spec has it as Phase 4 with its own
  schema. Every doc in the repo understated the scope by a whole phase.

The operator supplied the spec text, and set the priority explicitly: **parts 4
and 5 — Networking, and Study/Practice — are the prize.** They are the biggest,
hardest, most data-dependent work in the project and the reason a student would
open the tool at all. Parts 1–3 get finished first because 4–6 read from all
three, not because they matter more.

Deployment work (batch ingest writes, `posting_terms`, auth) is parked until the
product is whole. None of it changes what the product does.

## What was built

### Discover

- **Tracked state on every posting.** `PostingSummary` carries the board stage or
  nothing at all — "not on the board" is not a stage. Two extra queries for a
  whole page via `states_for_postings`. The card marks it and the posting window
  stops offering "Save" on something already applied to.
- **The transition table moved to the server.** `NEXT_EVENTS` lived in
  `TrackBoard.tsx`; the board and the posting window both needed it and two
  copies drift. Now `applications.NEXT_EVENTS` and served on the response.
- **Seven filters that already existed got exposed.** `PostingFilters` supported
  sponsorship, states, remote, posted-within, search and employment type —
  indexed and working — and `FilterBar` offered three of ten. `/api/discover`
  was widened to accept them too.
- **The eligibility check reached the UI.** The backend has computed graduation-
  window eligibility since session 2 and nothing rendered it. Silent on
  `not_stated`, which is most postings.

### Corpus

- **The story bank** — `corpus_stories` finally has a consumer. STAR fields,
  competency tags, and the zero-fabrication trace rendered ("Built from: …").
  Coverage is computed from tags the operator applied, never inferred from the
  prose: guessing that a story "sounds like conflict" claims a coverage they
  never made, and they find out in the room. Over-reliance is reported only at
  four or more stories, because three on one project is three stories, not a
  pattern.

### Track

- **Résumé versions, end to end.** Save one from the résumé check page, pick it
  on an application, and the board reports per-version outcomes. A rejection
  counts as a response — dropping it would flatter whichever version collected
  the most silence. Counts only, at any sample size.
- **Notes on applications**, via `PATCH /api/applications/{id}`. Notes and which
  résumé went out are corrections to a record, not things that happened on a
  date, so they are edits rather than log entries.

### Frontend

- **`react-router`**, at four pages rather than at twelve. The posting window has
  its own URL and survives a reload — verified in a real browser.

## Bugs found, all by running against live data

| Bug | Consequence |
|---|---|
| `_DEADLINE_RE` matched the bare word "deadline" | "You work well under tight deadlines" was reported as the posting's closing date. Roughly half of all extracted deadlines were soft-skills bullets. Every branch now requires application context; coverage went from a padded 10.8% to a correct 6.4% |
| `_GPA_RE` had no scale bound | "a current GPA of 8.00" — a ten-point scale — rendered as a GPA requirement beside four-point postings. Out-of-scale figures are dropped, not converted; the posting never said which scale it meant |
| `canonical_company` split initialisms | "D. E. Shaw" → `d e shaw`, missing a tier table keyed on `de shaw`. An elite quant firm sat in Target labelled "a realistic match at a realistic bar" |
| Suffix stripping could eat the whole name | Caught by the live run: "H&CO" → `h and` → `h`. A one-character blocking key matches everything it meets |
| Company rows split across normalisations | Live: 7 merges — AWS/Amazon, D. E. Shaw ×2, IMC, SIG/Susquehanna, Merck, Kearney. D. E. Shaw went 1 → 16 postings, IMC Trading 34 → 40 |
| Untrack orphaned its events | 15 application events against 3 applications. `events.discard` now removes them; untracking means "this was a mistake", not "this ended" |
| The gap list starved | `in_demand(limit=gap_limit * 6)` filtered *inside* a fixed window, so a good corpus returned fewer gaps while real ones sat just below it |

**A near miss worth recording:** the first verification pass ran against a
leftover uvicorn on :8077 serving pre-change code, and `curl /health` answered
`ok` the whole time. `/api/corpus/stories` returning 404 is what gave it away.
Check that the server you are testing knows about the code you just wrote.

## Decisions

| Decision | Rationale |
|---|---|
| Parts 4 and 5 are the prize; 1–3 are the foundation | Study needs company intelligence, Practice needs real rubrics, Networking needs the corpus. Building the prize on an 80% foundation wastes it |
| Networking is Phase 4, not deferred | The spec has it; the build plan lost it |
| `core/llm.py` will be sized for a live mock, not one-shot extraction | Multi-turn session state retrofitted later means rewriting every caller |
| Per-posting requirement extraction gets persisted | It is what makes "what should I study, based on where I applied" a query rather than a re-parse of every JD |
| Deployment stays parked | None of it changes what the product does |

## Current state

533 tests (up from 467), ruff clean, typecheck clean, production build clean.
All four pages driven through a real browser against live data: no console
errors, no failed requests, deep links survive reload.

The Safety lane is empty at the page size the UI requests (Reach 20, Target 19,
Safety 0). Not a lane-logic bug — `assign_lane` requires selectivity ≤ 1 and the
seed table has five companies at that tier. Documented in `KNOWN_GAPS.md`; the
fix belongs with Company Intelligence, which will have real data. Tuning
thresholds against a corpus that is still a stranger's would be fitting to noise.

## Second pass — driving it as a first-time user

The audit above was against the spec. This one was against the app: open it
cold, with an empty corpus, and use every feature. It found more than the spec
audit did, and all of it was invisible from the code.

**Only 20 of 9,197 applyable postings were reachable.** The three lanes were
capped at twenty each with no pagination anywhere in the UI, and the list simply
stopped — indistinguishable from the end of the market. Lanes now report what
they are holding back (`20 of 118`) and there is a "show more"; the scored slice
is bounded so a deep page cannot turn into a full-table scan.

**A new user was told they matched nothing.** With an empty corpus every score
rendered as a confident `0`, and the summary read *"0 terms evidenced, no
significant gaps"* — reassurance, on a page where the truth was that nothing had
been compared. A score of 0 against an empty corpus is an absence of data, not a
verdict, and reporting it as one is exactly the invented claim this project
refuses to make. The meter renders an em dash, the summary says what is actually
true, and Discover carries a banner explaining it with a route to fix it.

**The Safety lane could never populate, and the cause was not the threshold.**
`assign_lane` was asymmetric: `selectivity >= 4` meant Reach on selectivity
alone, but `selectivity <= 1` demanded a *corroborating* strong match before it
would call anything a Safety. Since only ~5% of postings carry a description,
most matches are thin, so a thin match at an accessible company fell through to
"Reach — too few comparable terms to judge fit". An IBM posting is not a reach
for anybody. Selectivity is a fact about the company that holds whether or not a
match could be computed, and both ends now treat it that way.

Underneath that sat a sampling bias worth recording: descriptions come only from
Tier 3, and the Tier 3 seed list was **entirely elite and high-tier**. Over a
400-posting scored slice: 141 elite, 137 high, 121 mid, 1 accessible. The
postings the operator could evaluate best were the ones they were least likely
to get. Ten mid-tier boards were added, each slug hit live first.

**"15 need attention" in the masthead led nowhere.** A count of broken feeds you
cannot open is a problem you learn to ignore. It is now a button onto a panel
that separates "parse looks broken" (row count collapsed, prior data kept) from
"could not be reached" (usually a board slug that changed), because those need
different fixes.

**Redundancy removed rather than added.** `POST /api/ingest/run` was a
synchronous ingest superseded by the background runner — the wrong shape twice
over, since a run takes a minute and a frozen host would kill it halfway.
`GET /api/ingest/cycles` duplicated `/api/cycles`. `GET /api/corpus/competencies`
was mine from earlier in the session and had no consumer.

Two pieces of lane copy were also overclaiming after the logic change: Safety's
blurb still promised "strong match", and an empty Target said "nothing with the
current filters" when the real reason was that nothing had enough text to judge.

547 tests. Verified in a browser twice — once cold with an empty corpus, once
populated — with no console errors and no failed requests.

## Part 4 — Networking

Built next at the operator's direction, ahead of Company Intelligence. It needed
the provider layer first, so that got built too.

### `core/llm.py`

Sized for the hardest consumer rather than the nearest one: a `Conversation`
carries rolling state and structured notes, because a behavioural mock has to
remember what was said three minutes ago and retrofitting that later would mean
rewriting every caller.

Every call has a rule-based fallback and the template lives with the *caller*,
which is deliberate — with no key configured, which is the default, the
deterministic path is the product, so a caller without a real template is a
caller that has not finished. A provider that raises for any reason (quota,
network, malformed response) degrades rather than erroring: from the caller's
side those are the same event.

**The grounding contract is narrow on purpose.** It checks figures in the output
against the corpus facts the caller declared, and nothing else. A general "is
this supported" test is either hand-waving or another model call, whereas a
number that appears nowhere in the operator's own record is specific and
checkable — and it is the one that gets repeated out loud in an interview.
Years and small counts in prose are exempt so the report stays worth reading.

### The module

- **`contacts.py`** — state folded from an interaction log, same shape as the
  application board. No status column, so the follow-up engine works from real
  dates and a correction adds a row.
- **`cadence.py`** — the deterministic follow-up engine. Seven days to the first
  chase, fourteen to the second, then **stop**: a third message does not get
  answered, it gets you remembered for the wrong reason. Once exhausted it says
  so and produces nothing further, rather than accruing a guilt counter.
- **`capture.py`** — the compliant way names get in. The operator uses LinkedIn's
  own Alumni tool, selects the results and pastes; the parser is tolerant and
  returns drafts for review. Nothing is fetched and no account is touched.
- **`drafts.py`** — both specific details are *sourced*, not generated. The thing
  about them comes from a real posting on their company's own board; the thing
  about the operator comes from a corpus fact, with the fact ids attached. An
  empty corpus refuses outright.
- **`alumni.py`** — the useful question is not "who do I know" but **which target
  companies do I know nobody at**, because that is the list an hour of work can
  change. Live: Jump Trading with 48 open roles and nobody at it.
- **`referrals.py`** — a referral is an event tied to an application, so the
  funnel can split referred from cold. Only `referral_confirmed` counts; an
  unanswered ask is the cold case wearing a hopeful label.

### Defects found, all by running it

| Defect | Consequence |
|---|---|
| `dict()` over a SQLAlchemy `Result` | `GET /network/contacts` 500'd. Pure-function tests would never have caught it; the first real call did |
| A thank-you counted as an unanswered message | Every warm relationship read "Awaiting reply" forever, with a false "6 days since you wrote, no reply" under a thread going fine. Only messages that put the ball in their court count now |
| Locations parsed as people | "San Francisco Bay Area" and "New York, NY" are capitalised, digit-free and the right length. LinkedIn puts one under every single person |
| Draft pulled three résumé bullets as its "one detail" | Corpus bodies have no sentence punctuation until the end, so splitting on "." returned the whole entry. 99 words of bullets in a cold email |
| Two identical drafts offered for non-cold kinds | Only the cold-outreach template has two registers. Identical drafts look like a choice and cost the reader the time to find out they are not |

The autogenerated migration also swept in unrelated drift — nullability on
`operator_profiles`, a unique constraint swapped for an index, an index on
`postings.role_family`. It was scoped by hand to the two new tables: a migration
that quietly alters other tables is how a rollback stops being safe. That drift
is real and still needs its own revision.

601 tests. Verified in a browser: paste → review → save, the due queue, drafts
with their provenance, no console errors.

## What the next session should pick up

1. **Company & job intelligence.** Cycle-open timing first: it needs no LLM and
   no new source, just a query over `posted_at` grouped by company × term × role
   family. Then H1B/LCA for real sponsorship and pay bands, then the reports
   pipeline. It also upgrades Networking's draft hooks from "a posting on their
   board" to real specificity hooks.
2. **Study & Practice** — the biggest thing in the project.
3. The schema drift above, in its own migration.
