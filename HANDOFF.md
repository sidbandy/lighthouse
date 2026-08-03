# Lighthouse — Project Handoff

A complete brief for continuing this project in a new session. Read this top to bottom before writing code. It covers what Lighthouse is, why it exists, every decision and constraint, what is built, how it works, how to run it, and exactly what to build next.

---

## 1. What Lighthouse is

**Lighthouse is a single-user, self-hosted command center for the internship and new-grad job search.** It is being built by and for the operator (Sid), a student, but is meant to help friends too — and it is explicitly designed to serve **any major**, not just CS: business, finance, consulting, engineering, design, marketing, and science students face the same broken pipeline.

The thesis (from the spec): **the phases of a job search are not independent, and the value is in the connections between them.** Knowing a company's interview format should change what you study; knowing which applications are high-match should change where you spend prep time; a behavioral answer should draw from the same store of facts your resume does. Commercial tools each solve one slice (Simplify aggregates postings, Teal scores resumes behind a paywall, Huntr tracks applications, Pramp does peer mocks) and none of them talk to each other. Lighthouse is the one tool that connects them.

The name: a lighthouse gives lost students clarity and direction in a chaotic job market.

**The spec** is `LIGHTHOUSE_SPEC.md` in the repo root (written under the project's old working name "Beacon" — the code is all "Lighthouse"). It defines six phases: Discover, Track & Tailor, Company Intelligence, Networking, Study, Practice, plus a cross-cutting Briefing. **The full build plan** is at `~/.claude/plans/ik-it-says-beacon-toasty-pebble.md` — read it; it has the source catalog, module-by-module design, and the operating principles.

---

## 2. The competitive edge (what makes this worth building)

Everything serves one of these:

1. **Every cycle, not just Summer.** Every popular list is organized around one Summer cycle and goes stale in November. Lighthouse's season resolver auto-advances, so off-cycle (Fall/Winter/Spring) roles — far less competition, far worse tooling — are first-class.
2. **Apply in the first days, not the last.** Roles close fast on rolling review. Lighthouse pulls ~95 sources, dedups, and can alert on new high-match postings; it also knows when a company's cycle historically opens.
3. **One deduped list instead of nine tabs.** The same role on Simplify + vansh + Indeed collapses into one row that shows "seen on 4 lists."
4. **Don't waste applications on dead postings.** A transparent ghost-job signal checklist.
5. **Reach a human.** The ATS parse-safety checker shows you *exactly* what the parser extracts, so a mangled resume never silently sinks you.
6. **Tailor with evidence, not guesswork.** Per-posting: what they require vs prefer, what your resume already covers, what to reword, and real gaps — never keyword-stuffing.
7. **Any major.** Finance/consulting/design/engineering/science are first-class in the taxonomy and skill vocabulary.

---

## 3. Operating principles (NON-NEGOTIABLE — the operator cares deeply)

These constrain every feature. Violating them is the fastest way to lose the operator's trust.

- **No invented numbers.** Never fabricate probabilities, predicted outcomes, or models fitted to tiny samples. Show **observed counts, real dates, cited ranges**, and let the operator conclude. No "75% likely ghosted," no Bayesian priors on funnel rates, no mastery scores, no readiness percentage. Where the spec proposed those (§9.2 Bayesian priors, §10 ML), we deliberately substitute transparent counts and honest "not enough data yet" states. This was reinforced by the operator multiple times.
- **Zero fabrication.** Any generated artifact references ≥1 real corpus fact. The resume tailor will **never** suggest a keyword the operator can't back up — a term with no corpus support is reported as a *real gap*, not a keyword to insert.
- **Show the inputs.** Every score, bucket, and ranking exposes the signals that produced it. A match score sits next to the exact terms that produced it; the term-resolution shows "stated by source" / "from description dates," never a confidence number.
- **Honest over impressive.** A thin-evidence match renders in muted grey, never the confident color, so a 100 computed from three title words reads as tentative. "Insufficient data" is an acceptable, honest state.
- **Compliance is architectural.** No LinkedIn scraping (the operator's own LinkedIn is needed for the search; and it violates their ToS). No auto-apply. No live-assessment assistance. JobSpy (a scraper lib) is configured with LinkedIn hard-disabled.

## 4. Working preferences (from the operator)

- **Generalize beyond CS.** Business/finance/engineering/design/science majors must be able to use it effectively.
- **Build the complete base product first.** Defer external-API integrations (Lightcast Skills, H1B data — see §11) until the product is whole and they're easier to slot in.
- **Git cadence: ~1 commit/day, one push/day at the END of a night working session** — and only after a full verification pass confirming no errors and the foundation works flawlessly. Remote is `sidbandy/lighthouse`. **As of this handoff, everything is committed to local `main` but NOT pushed** unless the end-of-session verification+push has happened.
- **Quality bar:** features must be genuinely well-engineered and complex — "more complex and well thought out than I could do on my own," clean and professional, not "vibe-coded B2B SaaS." Invest in the design.
- **Use subagents for menial parallel work** (test-writing has been delegated repeatedly and works well), but don't over-spawn.
- **Cite/verify, don't assume.** Many bugs were caught by running against live data rather than trusting the design. Keep doing that.

---

## 5. Tech stack & environment

- **Backend:** Python **3.12 (arm64)** — venv at repo root `.venv`, created from `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`. (Note: system default `python3` is 3.14 which lacks some ML wheels — always use `.venv`.) FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, httpx, rapidfuzz.
- **Database:** local **PostgreSQL 16** (Homebrew, `postgresql@16`), database `lighthouse`, connection `postgresql+psycopg://localhost/lighthouse`. **pgvector 0.8.0** was built from source against pg16 (the Homebrew bottle only ships pg17/18 builds). The `Vector(384)` column exists on postings/corpus but is currently unused (see §7 on embeddings).
- **Frontend:** React 18 + Vite + TypeScript + Tailwind v3. **Light "lighthouse" theme** — cream `paper` page, white cards, one `navy-*` ramp for structure and type (low = light, conventional order), `beacon-*` orange spent only on the primary action and the live figure. Lane accents reach/target/safety. The navy masthead is the only dark band on the page. `web/` dir; Playwright is a devDependency for screenshot verification. **There is no dark mode and none is planned.**
  - Two classes of bug have bitten this theme twice: a utility referenced but never defined in `tailwind.config.js` is *silently dropped* rather than erroring (`mist-500`, `font-600` — nothing was bold for weeks), and a sweep that globs only `*.tsx` misses `lib/format.ts`. After any token change, grep for the old names across `*.ts` too, and probe a computed style in the browser rather than trusting the diff.
- **Hard constraint — the operator's machine is an Apple M3 with 8 GB RAM.** This is why there is **NO torch / sentence-transformers** — a ~2 GB install is off the table. Match scoring is pure-lexical BM25 (see §7). Any future embeddings/voice must be local and light, or deferred.
- **LLM:** none wired yet. When needed (mock interviews, extraction), use **Gemini free tier** (operator is low on Claude credits), behind a provider interface with a rule-based fallback so everything degrades gracefully offline. Not built.
- **No Docker in use** — local Postgres is the dev path. A `docker-compose.yml` exists for future deploy-readiness only.

---

## 6. How to run it

```bash
# from repo root /Users/sid/Downloads/lighthouse
# --- backend API ---
.venv/bin/uvicorn lighthouse.api:app --app-dir backend --port 8077 --reload
# health: curl localhost:8077/health   |   docs: localhost:8077/docs

# --- frontend ---
cd web && npm install && npm run dev   # serves on :5173, expects API on :8077

# --- CLI (no server needed) ---
PYTHONPATH=backend .venv/bin/python -m lighthouse.cli ingest --max-tier 3   # fetch/refresh postings
PYTHONPATH=backend .venv/bin/python -m lighthouse.cli discover --role quant  # three-lane view
PYTHONPATH=backend .venv/bin/python -m lighthouse.cli postings --season summer --year 2027
PYTHONPATH=backend .venv/bin/python -m lighthouse.cli cycles       # applyable cycles + counts
PYTHONPATH=backend .venv/bin/python -m lighthouse.cli sources      # per-source health

# --- tests / lint / migrations ---
.venv/bin/pytest backend/tests -q          # 467 passing
.venv/bin/ruff check backend               # clean
.venv/bin/ruff format backend
cd backend && ../.venv/bin/alembic upgrade head
```

There is a `Makefile` at the repo root with `install/dev/test/lint/fmt/migrate/db-reset` targets. Config is via env vars prefixed `LIGHTHOUSE_` (see `.env.example`); defaults work out of the box for local dev.

---

## 7. Architecture & how the pieces fit

```
backend/lighthouse/
├── api.py            # FastAPI app; includes the routers below
├── cli.py            # ingest / discover / postings / cycles / sources
├── core/
│   ├── config.py     # pydantic-settings; DEFAULT_OPERATOR_ID (singleton user)
│   ├── db.py         # engine, session_scope(), get_session() dependency
│   ├── models.py     # ALL SQLAlchemy models (see §8)
│   ├── corpus.py     # the operator's facts/stories: CRUD, zero-fab enforcement
│   ├── resume.py     # PDF -> draft facts (pdfplumber); raw text for ATS check
│   ├── events.py     # the append-only log: record / history / history_for_many
│   ├── onboarding.py # empty -> usable: resume, projects, targets, constraints
│   ├── schemas.py    # Pydantic shapes for corpus + onboarding
│   ├── router.py     # /api/corpus/*, /api/onboarding/*, /api/companies/search
│   └── textanalysis.py # tokenizer/stemmer, TECH_TERMS + DOMAIN_TERMS vocab, phrases
├── ingest/
│   ├── seasons.py    # Cycle, applyable_cycles(today) -> auto-advancing cycles
│   ├── terms.py      # term-resolution cascade (explicit->title->desc dates->eligibility)
│   ├── normalize.py  # canonical company/url/title, gh_jid extraction, location parse,
│   │                 #   classify_role_family (ALL majors), classify_employment_type
│   ├── base.py       # RawPosting dataclass + Connector ABC + build_client()
│   ├── table_parser.py # tolerant markdown-table parser (multi-table, ↳, <details>, emoji)
│   ├── dedup.py      # cross-source dedup (gh_jid veto, canonical url, fuzzy title)
│   ├── registry.py   # declarative list of Tier 1-2 sources
│   ├── ats_targets.py# Tier 3 board seeds + auto-discovery from posting URLs
│   ├── pipeline.py   # run_ingest(): fetch (isolated per source) -> dedup -> persist
│   ├── health.py     # (source_health tracking lives in models + pipeline)
│   ├── router.py     # /api/ingest/*
│   └── connectors/   # simplify.py, markdown_repo.py, ats.py (greenhouse/ashby/lever/SR)
├── discover/
│   ├── coverage.py   # corpus x market: per-fact reach/unique-reach, corpus-wide gaps
│   ├── match.py      # BM25 CorpusIndex + 3-bucket keyword output (evidenced/reword/gap)
│   ├── ghost.py      # ghost-job signal checklist (facts, NO probability)
│   ├── lanes.py      # company selectivity tiers + reach/target/safety assignment
│   ├── ranking.py    # score_postings, three_lane_view, index cache, serialization
│   ├── service.py    # PostingFilters, list_postings, cycle_counts, source health
│   ├── schemas.py    # Pydantic response shapes
│   └── router.py     # /api/postings, /api/discover, /api/cycles, /api/sources/*
└── track/
    ├── applications.py # apply->funnel state machine, folded from the event log
    ├── funnel.py     # observed counts + conversions, refuses rates on tiny samples
    ├── ats_check.py  # geometry-based ATS parse safety + parse preview (THE resume feature)
    ├── tailor.py     # per-posting requirement extraction (required/preferred/knockouts)
    ├── schemas.py    # AtsReportOut, TailorReportOut
    └── router.py     # POST /api/resume/check, POST /api/postings/{id}/tailor

web/src/
├── api/{client.ts,types.ts}   # fetch wrapper + hand-written types mirroring schemas
├── components/
│   ├── Header.tsx             # masthead, cycle counts, source-health dot, Discover/Resume nav
│   ├── FilterBar.tsx          # role families (ALL majors), seasons, description-only toggle
│   ├── LaneColumn.tsx, PostingCard.tsx   # the three-lane Discover view
│   ├── MatchMeter.tsx, TermChips.tsx     # score (muted when thin) + 3-bucket keywords
│   ├── PostingDrawer.tsx      # posting detail: match, TailorPanel, ghost, sources, description
│   ├── TailorPanel.tsx        # per-posting tailoring inside the drawer
│   ├── GhostChecklist.tsx     # ghost signals
│   ├── ResumeCheck.tsx        # the resume-check page (upload)
│   ├── ParsePreview.tsx       # THE centerpiece: what-you-see vs what-the-ATS-extracts
│   ├── AtsFindings.tsx        # severity-ranked findings with fixes
│   ├── CorpusPage.tsx         # the corpus page: orchestrates everything below
│   ├── CoveragePanel.tsx      # corpus vs live market: reached/unreached + real gaps
│   ├── FactList.tsx           # facts by type, each showing its reach + unique reach
│   ├── FactEditor.tsx         # create/edit one fact
│   ├── ResumeImport.tsx       # PDF -> drafts -> operator review -> corpus
│   ├── SetupPanel.tsx         # target companies + constraints
│   ├── TrackBoard.tsx         # the application board, grouped by stage
│   └── FunnelPanel.tsx        # stage counts, conversions, real wait times
└── App.tsx                    # view switch (discover | track | corpus | resume)
```

**Data-flow spine:** everything personal reads/writes the **corpus** (`corpus_facts`, `corpus_stories`) and appends to the **event log** (`events`, append-only, `occurred_at` vs `recorded_at`). Modules never call each other's internals — they go through corpus + events. Shared tables (postings, companies, source_health, reported_questions) have no `user_id`; personal tables have a nullable `user_id` defaulted to a single hardcoded operator UUID — this split is what makes multi-user later a config change, not a rewrite.

**Why BM25 and not embeddings:** the match score's *primary* output is the keyword-gap list, not the number. A lexical approach means every term is traceable to a literal word (satisfies "show the inputs") and it needs zero heavy dependencies (satisfies the 8 GB RAM limit). The score is **coverage** — the weighted share of the posting's emphasized terms the corpus can evidence — not a normalized BM25 total (which was an early bug that compressed everything to 0–7). Thin-evidence matches (few comparable terms) are flagged and ranked below reliable ones. `Vector(384)` columns remain in the schema so semantic search can be added later if it ever earns its weight.

---

## 8. Data model (key tables in `core/models.py`)

- **Company** (shared): `canonical_name` (dedup blocking key), `ats_vendor`/`ats_slug`/`careers_url`, `tier` (**selectivity only** — see `OperatorTarget`).
- **OperatorProfile** (personal): singleton per `user_id`. Constraints — preferred locations, remote, sponsorship stance, weekly study hours, target cycles. Onboarding writes it; `constraints_set` reads it.
- **OperatorTarget** (personal): "I want to work here", one row per (user, company). Deliberately **not** a flag on `Company`: wanting a company is a fact about the operator, not about the company.
- **Posting** (shared): the canonical deduped posting. `canonical_url` (dedup key), `ats_job_id` (identity veto), `season`/`term_year`/`term_rule`/`term_evidence`, `employment_type`, **`role_family` (now a STRING column, not enum — so the taxonomy can grow)**, `sponsorship`, `locations` (JSONB superset), `description`/`description_available`, `is_active`, `posted_at`, `embedding` (unused).
- **PostingSource** (shared): provenance, one per (posting, source) sighting; `source_fingerprint` makes re-ingest idempotent. Enables "seen on N lists."
- **SourceHealth** (shared): per-source `last_success_at`, row counts, `consecutive_failures`, `is_quarantined` (trips when a run returns <50% of prior rows).
- **CorpusFact** (personal): `fact_type` (project/experience/skill/achievement/education), title/body, `meta` JSONB, embedding.
- **CorpusStory** (personal): STAR fields + `source_fact_ids` (zero-fab: empty = unverified).
- **Event** (personal): append-only state log.
- **Application, ResumeVersion, ReportedQuestion, PracticeAttempt**: defined, mostly awaiting the Track/Study modules.

Enums are Python `StrEnum` (Season, Sponsorship, RoleFamily, EmploymentType). `RoleFamily` is deliberately stored as a string column (migration `8f4fa0b9cc52`) so new families don't need an ALTER TYPE; `fact_type` and `term_rule` are likewise plain strings.

---

## 9. What is BUILT and working (18 commits, 467 tests passing, clean lint)

**Ingestion (Discover phase 1 — the first useful milestone, DONE):**
- **~95 sources across 3 tiers.** Tier 1: Simplify's structured `listings.json` (internships + new-grad; carries a `terms` array spanning all cycles — this is what makes off-cycle coverage possible). Tier 2: 11 curated markdown repos (vansh, speedyapply, zapplyjobs, jobright, sndsh, NUFT quant). Tier 3: direct ATS JSON APIs (Greenhouse/Ashby/Lever/SmartRecruiters) — ~27 verified seed boards + auto-discovery from posting URLs. **Tier 3 is the only tier with full descriptions**, which match scoring and tailoring need.
- **Season resolver** auto-advances cycles; **term-resolution cascade** (only ~5% of titles name their season, so this is required) records *which rule* fired, never a confidence number; unresolved = "term unknown," filterable, never guessed.
- **Cross-source dedup**: company blocking → `gh_jid` job-id veto → canonical URL → fuzzy title. Keeps all `source_ids`.
- **Per-source isolation + health**: one dead source never kills a run; <50%-rows trips quarantine.
- Live numbers: ~37k raw → ~27.5k deduped; ~400+ with descriptions; role families populated across all majors (swe 2936, other 2068, ai_ml 811, data, quant, marketing 203, business 157, design 153, science, mechanical, consulting, finance…).

**Discover (DONE, backend + frontend):**
- BM25 match scoring with the three-bucket keyword output (evidenced / phrase-to-mirror / genuine gaps), company-name filtering, thin-evidence flagging.
- Ghost-job signal checklist (facts only, no probability).
- Three-lane view (reach/target/safety) from match × company selectivity, with weekly quotas.
- Full React UI: header with live cycle counts + source health, filter bar (all role families), three lanes, posting cards (score muted when thin), detail drawer.

**Corpus & onboarding (DONE, backend + frontend):**
- Corpus CRUD with zero-fabrication enforcement; resume PDF → draft facts (operator reviews, never auto-committed); onboarding flow (resume → projects → targets → constraints).
- **The API layer** (`core/router.py`): facts CRUD, `POST /corpus/extract` (drafts, nothing saved) and `POST /corpus/facts/bulk` (commit the reviewed batch) as deliberately separate calls, `GET /corpus/coverage`, onboarding state, targets, constraints, company search. Every corpus write invalidates the match index so the next score reflects the edit.
- **The corpus page** — the "My corpus" tab. What makes it more than a CRUD form: **every fact shows what it's actually worth in the live market.** Per fact, using the same signal rule the per-posting match uses: the skill terms it contributes, how many ingested postings mention each (`reach`), and how many *no other fact reaches* (`unique_reach`). That last number is the honest answer to "is this pulling its weight?" — on the seeded corpus it correctly showed the standalone `Go`/`React`/`TypeScript` skill facts adding zero coverage the Cloudify and Ledger entries didn't already give.
- **Corpus-wide coverage** (`discover/coverage.py`): reached/unreached over a stated sample of postings that carry a real description, plus the most-demanded terms no fact evidences. Filterable by role family. Gaps are restricted to recognised skill vocabulary — without that the list fills with "engineer", "software", "technology", which is noise dressed as insight. Cached per role filter, keyed on posting count + last sighting.

**Track — the resume features (DONE, the operator's stated priority):**
- **ATS parse-safety checker** (`ats_check.py`): geometry-based. Detects multi-column layouts and shows the **parse preview** — the resume re-extracted the way a naive ATS reads it, side by side with the intended layout, so you SEE the scramble. Also: contact-in-header/footer (dropped by ~25% of ATS = auto-reject), ligatures, decorative/non-ATS fonts, risky bullet glyphs, non-standard section headings, image-only PDFs. Ranked worst-first, each with a concrete fix. Grounded in how Workday/Greenhouse/Taleo actually fail. Full UI at the "Résumé check" page.
- **Per-posting tailoring** (`tailor.py`): reads one JD closely — required vs preferred (weighted differently), hard knockouts (years/degree/authorization/graduation/location), and three honest buckets with specific per-item advice ("you have this but it's not on the resume you pasted — put it in a bullet"). **Strips legal/EEO boilerplate** before extracting (this was the key fix — "reasonable accommodation" was being read as a required skill). Coverage % with the honest edits that would raise it. Now surfaced as a **panel inside the posting drawer** (paste resume text optional) AND as a standalone endpoint.

**Track — the application board (DONE, backend + frontend):**
- **Event-sourced.** `Application` has no `status` column: state is folded from the append-only `events` log (`core/events.py`) on every read. That buys dates rather than states, additive corrections, and measurable silence — a mutable status field can answer none of the three.
- **Ghosting as a dated fact.** "31 days since you applied, no response" — a subtraction between two real dates, never a probability. Suppressed at 0 days, because a true-but-useless line on every fresh row trains you to ignore the one that matters at day 40.
- **The funnel refuses false precision.** Conversions are all measured from *Applied* (a consecutive-pair rate would assume every application walks the same path — real ones skip the OA entirely), shown as "3 of 12 (25%)" with both numbers, and below `MIN_SAMPLE`=10 it says "too few to read anything into yet" instead of a percentage. Wait times are observed medians with n and range; under n=3 it lists the raw observations rather than computing a median from one point.
- **Two bugs worth remembering, both found by running the logic rather than reading it:** stage counts originally used `>=`, so an application that went straight from applied to interview counted as having "reached assessment" — inflating a stage it never touched. And `total` counted saved-but-never-applied bookmarks, so "across 12 applications" sat above conversions all measured out of 6.
- One-click save / "I applied" from the posting drawer; the board groups by stage and offers only the transitions that make sense from where a row actually is.

**Generalization (DONE):** role taxonomy + skill vocabulary + classifier all cover finance/consulting/business/marketing/design/mechanical/science, verified on real titles.

---

## 10. What is NOT built yet (the roadmap, roughly in priority order)

The plan's build sequence is Discover → Track → Company Intel → Study → Practice → Briefing. Discover is done; Track is mostly done (resume features shipped; the application board + funnel below are not).

1. **Stories UI + corpus depth.** `corpus_stories` (STAR + `source_fact_ids`) has a service layer and zero-fab enforcement but no UI and no consumer yet — it unlocks once Study/Practice land. Corpus staleness nudges are also unbuilt (every seeded fact shares one `created_at`, so there is nothing real to show yet).
2. **Track — remaining pieces.** The board, the event-sourced funnel and one-click apply-and-log from Discover are DONE. Still missing: **back-dating events from the UI** (the API takes `occurred_at`, the board never sends it — see KNOWN_GAPS, highest-value item), resume-version tracking (`ResumeVersion` model exists, nothing writes it), free-text notes, and comparison against cited published baselines.
3. **Company Intelligence (§4).** `company_processes` (interview format/rounds/rubrics), expected wait times (real reported gaps, sample size shown), a **cycle-open timing model** from historical posting dates ("Optiver's Summer roles posted early July the last 2 years"), timezone-correct multi-stage deadline calendar with ICS export, specificity hooks. Population is semi-automated (Reddit/LeetCode → extraction → operator review) — needs the Gemini LLM layer.
4. **Study (§6).** Company-weighted problem intelligence (real reported counts), per-pattern attempt records (transparent, no mastery score), SM-2 spaced repetition tolerant of missed days, deterministic study-plan scheduler, competency-tagged story bank with coverage matrix, TMAY builder. Reuse the recency-weighting helper.
5. **Practice (§7).** Behavioral first (needs no sandbox): fully-LOCAL voice loop (Web Speech live captions + whisper.cpp transcript + Piper TTS — all local per the RAM constraint), deterministic Layer-1 delivery metrics (filler/WPM/silences — no LLM), Layer-2/3 feedback via Gemini with rule-based fallback and the hard zero-fabrication constraint. Then technical mocks + a sandboxed code runner (Docker, no network, resource caps) as the final isolated phase.
6. **Briefing (§8).** Weekly digest, effort-allocation triage, readiness gate → a finite dated checklist (not a score). Cross-cutting; needs the others first.
7. **The Gemini LLM provider layer** (`core/llm.py`, `provider ∈ {gemini, claude, rule_based}`) — needed by Company Intel extraction and Practice feedback. Not started. Every call must have a rule-based fallback.

---

## 11. External integrations researched (DEFERRED per operator — build the base first)

Saved in memory (`~/.claude/projects/-Users-sid-Downloads-lighthouse/memory/integration-candidates.md`). The two standouts:
- **Lightcast Open Skills API** — free, 34,000-skill taxonomy with an extraction endpoint. The single best upgrade to match scoring + tailoring (standardize skills, catch related ones the curated dictionary misses).
- **Public H1B/LCA data (US DOL)** — free (`h1bdata.info`, `h1bgrader.com`). Tells you which companies *actually sponsor* (a real sponsorship filter, not just the emoji flags) and real per-company salary bands.

Also viable/free: Reddit API (interview experiences), LeetCode GraphQL (company questions), Codeforces (quant CP ladder), HN "Who is Hiring." Dead: Clearbit Logo API (sunset Dec 2025 — use Hunter's free logo API instead).

Do NOT integrate these yet. The operator wants the complete base product first, then slot APIs in when the whole is easier to reason about.

---

## 12. Known rough edges / gotchas

- **The seeded corpus is still fake.** `corpus_facts` holds 12 facts from a *test* resume (Cloudify / Ledger / UT CS 2028) used during development — not the operator's real history. The "My corpus" page now exists to replace them; until it is used, every match score is scored against a stranger. Delete them and import a real resume first.
- **Some ATS seed board slugs are not the obvious guess** (`drweng` not `drw`, `optiverus` not `optiver`, `doordashusa` not `doordash`). Always verify a board slug live before adding it.
- **Tier 3 is opt-in per company**, not a blanket crawl (polite + avoids thousands of irrelevant requests). Boards you care about get auto-discovered from posting URLs.
- **JobSpy (Tier 4 aggregators) and the free remote feeds are planned but not yet wired** — only Tiers 1–3 are live in the registry.
- **The `underclassmen-internships` repo was intentionally dropped** — its table is a program directory (name/open-date/year), not postings. If re-adding, it belongs in the Companies module.
- **Bugs are best caught by running against live data**, not by trusting the design — this has held true repeatedly (multi-table attribution, location merging, idempotency, boilerplate pollution, score compression were all found this way). When building, hit the real DB and real feeds.
- **`docs/KNOWN_GAPS.md` is the parking lot, and keeping it current is part of the job.** When you find a narrow edge case, a suspicious number, or a half-wired capability that is *not* blocking what you are building — **write it there instead of fixing it**. Chasing every small thing mid-feature is how a session ends with three half-finished modules; the operator asked for it to work this way explicitly.
  - Each entry must state **the problem, why it happens, and how to fix it**, with a severity of `wrong` / `misleading` / `incomplete` / `cosmetic`. An entry that only says "X is weird" costs the next session the same investigation that produced it.
  - **Delete entries as they are fixed** — git history records what was fixed, that file records what is not, and a stale entry sends someone to look at working code.
  - The file also has a "Not gaps — deliberate" section. Read it before "fixing" something that looks wrong; several of those choices are load-bearing.
  - Subagent reports are a good source: test-writing agents are told to report suspicious findings rather than fix them, and those reports have twice surfaced real bugs. Triage them into either an immediate fix (if it produces a wrong number) or an entry in that file.
- **Push discipline:** commit ~daily, push once at night after a full verification pass (`pytest` clean, `ruff` clean, app runs, key flows work). Remote `sidbandy/lighthouse`.

---

## 13. Commit history (context for what happened when)

```
Generalize beyond CS + per-posting tailoring in the drawer
Tests for ATS check and tailoring, plus two fixes they surfaced
Resume-check UI: show the operator exactly what the ATS sees
Resume ATS parse-safety check and per-posting tailoring
Discover frontend: the three-lane view
Test suite for the corpus/match layer, plus vocab fixes
Three-lane ranking, wired through API and CLI
Corpus, resume extraction, and onboarding
Tier 3 ATS connectors, and a score that means something
Match scoring via BM25, with no ML dependencies
Ghost-job signals, CLI, and location reconciliation
API layer, plus a multi-table attribution fix
Ingestion engine: 13 live sources, cross-source dedup
Foundation: schema, season resolver, term resolution
```

Read commit messages for the "why" — they're detailed and explain the reasoning and the bugs found.

---

## 14. First moves in a new session

1. Read this doc, then `LIGHTHOUSE_SPEC.md` and the plan file.
2. `.venv/bin/pytest backend/tests -q` (expect 467 passing) and `.venv/bin/ruff check backend` (clean) to confirm a green baseline.
3. Start the API + frontend (§6), open localhost:5173, click through Discover and Résumé check to see the current state.
4. Recommended next build: **the Track application board + funnel** (§10 item 2) — Discover and the corpus are done, so the next real gap is what happens *after* you decide to apply. The models (Application, ResumeVersion, Event) already exist and nothing writes to them yet; note there is still no `core/events.py`, so the append-only event log has no helper.
5. Honor the operating principles (§3) and preferences (§4) in everything.
