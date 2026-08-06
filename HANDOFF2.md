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
