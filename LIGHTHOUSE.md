# Lighthouse

A self-hosted command center for the internship and new-grad search, built for
students of any major. This document is the full picture: what it is, why it
exists, the rules it is built under, what works today, what is coming, and how
every screen is meant to be used.

Written so someone joining the project can read it top to bottom and start
contributing without needing anything else.

---

## 1. The problem

The current state of the art for a student running a job search is a Google
Sheet, Ctrl-F on a GitHub markdown table, a Notion doc of resume versions,
LeetCode in another tab, and a friend for mock interviews. The commercial tools
each solve one slice — Simplify aggregates postings, Teal scores resumes behind
a paywall, Huntr tracks applications, Pramp does peer mocks — and none of them
talk to each other. Reproducing what Lighthouse does would take four
subscriptions and a spreadsheet.

**The thesis: the phases of a job search are not independent, and the value is
in the connections between them.** Knowing a company's interview format should
change what you study. Knowing which applications are high-match should change
where prep time goes. A behavioral answer should draw from the same store of
facts your resume does.

That is the whole product in one sentence. Every feature either creates one of
those connections or feeds one.

The name: a lighthouse gives lost students direction in a chaotic market.

---

## 2. What makes it worth building

Seven things no existing tool does. Everything in the codebase serves one of
them.

1. **Every cycle, not just Summer.** Every popular list is organised around one
   Summer cycle and goes stale in November. Lighthouse's season resolver
   auto-advances, so off-cycle Fall/Winter/Spring roles — far less competition,
   far worse tooling — are first-class.
2. **Apply in the first days, not the last.** Roles close fast on rolling
   review. Lighthouse pulls ~95 sources, dedups them, and knows when a company's
   cycle has historically opened.
3. **One deduped list instead of nine tabs.** The same role on Simplify, vansh
   and Indeed collapses into one row that says "seen on 4 lists".
4. **Don't waste applications on dead postings.** A ghost-job signal checklist
   where every signal is visible and nothing is hidden behind a score.
5. **Reach a human.** The ATS parse-safety checker shows exactly what the parser
   extracts, so a mangled resume never silently sinks you.
6. **Tailor with evidence, not guesswork.** Per posting: what they require
   versus prefer, what your corpus already covers, what to reword, and what is a
   real gap — never keyword stuffing.
7. **Any major.** Finance, consulting, design, engineering, marketing and
   science are first-class in the taxonomy and the skill vocabulary, not
   afterthoughts bolted onto a CS tool.

---

## 3. The rules

These are not preferences. They constrain every feature, and a change that
breaks one does not ship.

**No invented numbers.** Lighthouse never fabricates probabilities, predicted
outcomes, or models fitted to tiny samples. It shows observed counts, real
dates, and cited ranges, and lets the reader conclude. No "75% likely ghosted",
no mastery scores, no readiness percentage. Where a number would need more data
than exists, the honest answer is "not enough data yet", and that is an
acceptable thing to render.

**Zero fabrication, in both directions.** Any generated artifact references at
least one real fact from the corpus. The resume tailor will never suggest a
keyword the operator cannot back up — a term with no corpus support is reported
as a real gap, not a keyword to insert. The reverse matters just as much: a
false gap ("you don't have Postgres" when the corpus says PostgreSQL) is the
same failure seen from the other side.

**Show the inputs.** Every score, bucket and ranking exposes the signals that
produced it. A match score sits next to the exact terms that produced it. Term
resolution says "stated by the source" or "from description dates", never a
confidence number.

**Honest over impressive.** A thin-evidence match renders muted rather than
confident, so a score computed from three title words reads as tentative.

**Compliance is architectural, not a policy note.** No LinkedIn scraping — it
violates their terms, and the operator's own LinkedIn is needed for the search.
No auto-apply. No assistance during a live assessment. JobSpy, the scraper
library, is configured with LinkedIn hard-disabled in code.

**Students and new grads only.** Never "years of experience" — internships
completed, graduation term, coursework. Industry professionals are a different
product.

**Light theme only.** There is no dark mode and none is planned.

---

## 4. The six parts

The product is six phases plus a cross-cutting briefing. Two and a half are
built.

| # | Phase | What it does | State |
|---|---|---|---|
| 1 | **Discover** | Find every posting worth applying to, ranked and filtered | Built |
| 2 | **Track & Tailor** | Know the state of every application; tailor each one with evidence | Built |
| 3 | **Corpus + Company & job intelligence** | Your own facts; and the researched truth about who you're applying to | Corpus built, intelligence not started |
| 4 | **Networking** | Find alumni, reach out, get referrals, never drop a thread | Not started |
| 5 | **Study & Practice** | What to study and practise, and doing the reps out loud | Not started |
| 6 | **Week-of / day-of** | The weekly briefing and the day-of interview kit | Not started |

**Parts 4 and 5 are the prize.** They are the biggest, hardest, most
data-dependent work in the project, and they are what most students actually
need — one place that holds every study and prep need instead of six tabs.
Parts 1–3 are being finished first because 4, 5 and 6 all read from them:
Study's problem selection needs company intelligence, Practice's mock scoring
needs real interview rubrics, and Networking's outreach drafts need the corpus.
Building the prize on an eighty-percent foundation would waste it.

---

## 5. What works today

### Ingestion

**~95 sources across three tiers**, each connector isolated so one dead source
never kills a run.

- **Tier 1** — Simplify's structured `listings.json` for internships and new
  grads. Its `terms` array spans multiple cycles, which is what makes off-cycle
  coverage possible at all.
- **Tier 2** — 11 curated markdown repos (vansh, speedyapply, zapplyjobs,
  jobright, sndsh, the Northwestern quant list), read by a tolerant table parser
  that survives malformed rows, `↳` company carry-forward, `<details>`-wrapped
  location cells and emoji flags.
- **Tier 3** — direct public ATS APIs (Greenhouse, Ashby, Lever,
  SmartRecruiters), ~27 verified seed boards plus auto-discovery from posting
  URLs. **This is the only tier with full descriptions**, which match scoring
  and tailoring need.

Live numbers from the last full run: **36,221 raw rows → 26,566 after dedup**,
13/13 sources healthy, 1,690 new postings. Role families populate across every
major — swe 2936, other 2068, ai_ml 811, then data, quant, marketing 203,
business 157, design 153, science, mechanical, consulting, finance.

**Term resolution is a required engine, not a nicety** — only about 5% of job
titles name their season. An ordered rule cascade tries explicit title tokens,
then title patterns, then description date phrases, then eligibility language.
It records *which rule fired* and the text that triggered it. Anything
unresolved is labelled "term unknown", stays filterable, and is never guessed.

**Cross-source dedup** blocks by normalised company, then applies a job-ID veto
(a Greenhouse `gh_jid` mismatch is an absolute bar on merging), then canonical
URL, then fuzzy title. Locations merge to the superset. All source ids are kept
so the UI can say "seen on 4 lists".

**Source health** tracks last success, row counts and consecutive failures, and
quarantines a source that returns under half its previous rows. Sources rot;
Lighthouse says so out loud rather than absorbing it.

### Match scoring

Pure lexical BM25 over a curated skill vocabulary. **No torch, no
sentence-transformers** — the machine this runs on is an 8 GB M3, and a 2 GB
install is off the table. That constraint turned out to be a feature: every term
in a score traces to a literal word, which is exactly what "show the inputs"
requires.

The score is **coverage** — the weighted share of the posting's emphasised terms
the corpus can evidence — not a normalised BM25 total. The primary output is not
the number at all; it is three honest lists: terms already evidenced, terms the
operator has under different wording (adopt the posting's phrasing), and genuine
gaps. Thin-evidence matches are flagged and ranked below reliable ones.

### The rest, briefly

- **Ghost-job signals** — a checklist of facts (age, corroboration across
  sources, posted-versus-updated mismatch, description presence), never a
  probability.
- **Three-lane view** — reach / target / safety from match × company
  selectivity, with a suggested weekly quota per lane.
- **Posting brief** — pay, working pattern, length, deadline, GPA floor, named
  interview stages and responsibilities pulled out of the description, each with
  the sentence it came from. Measured over 400 real descriptions: pay 30%,
  length 20%, pattern 19%, process 10%, responsibilities 77%.
- **Eligibility check** — does the operator's graduation term clear the
  posting's stated window. Over 400 postings, 43 state a class year and 14 would
  knock out a 2027 grad. "Not stated" is the most common answer and is never
  dressed up as a pass or a fail.
- **ATS parse-safety check** — geometry-based, and the centrepiece is the parse
  preview: the resume re-extracted the way a naive ATS reads it, side by side
  with the intended layout, so a scrambled two-column layout is *seen*, not
  described. Also catches contact details in the header or footer (dropped by
  roughly a quarter of ATS, which is an automatic rejection), ligatures,
  decorative fonts, risky bullet glyphs, non-standard headings and image-only
  PDFs.
- **Per-posting tailoring** — required versus preferred, weighted differently,
  plus hard knockouts (years, degree, authorization, graduation, location).
  Strips legal and EEO boilerplate first; without that, "reasonable
  accommodation" gets read as a required skill.
- **The application board** — event-sourced. `Application` has no status column;
  the stage is folded from an append-only event log on every read. That buys
  real dates instead of states, makes a correction additive, and makes silence
  measurable.
- **The funnel** — conversions all measured from Applied rather than between
  consecutive stages, because real pipelines skip stages. Shown as "3 of 12
  (25%)" with both numbers, and under a sample of 10 it says "too few to read
  anything into yet" instead of a percentage.
- **The corpus** — the operator's facts and stories, with resume PDF import to
  drafts the operator reviews before anything is saved. Every fact reports what
  it is actually worth in the live market: which skill terms it contributes, how
  many ingested postings mention each, and how many postings *no other fact
  reaches*. That last number is the honest answer to "is this pulling its
  weight?"

**Verification at the last checkpoint:** 467 tests passing in about two seconds,
lint clean, typecheck clean, production build clean, all four pages driven
through the real UI with no console errors.

---

## 6. What is not built

In the order it is being built.

**Company & job intelligence.** The main function of part 3 and none of it
exists yet. Two layers: the company (interview process, evaluation rubric, when
their cycle historically opens, real wait times between stages, who actually
sponsors, real pay bands) and the job (the same intelligence resolved down to
one posting — which of the company's known stages this req's own description
names, this role family's historical open date rather than the company's, this
posting's stated pay against the company's real band).

The sourcing is researched and free: the posting history already in the database
gives cycle-open timing with no new source and no LLM; US Department of Labor
H1B/LCA disclosure data gives real sponsorship and real pay bands from one
dataset; Reddit and LeetCode give interview reports and reported questions;
company careers pages and engineering blogs give the specific, current details
that make a "why this company" answer land.

**Networking.** Contacts and outreach tracked with the same dated-facts
discipline as the application board. Capture is paste-in from LinkedIn's own
Alumni tool — a first-party feature built for exactly this — so no scraping is
involved. Outreach drafts are grounded in the corpus: under 120 words, one
verifiable detail about their team, one real fact about the operator, the trace
rendered, and Lighthouse never sends anything. A follow-up cadence with a
two-message limit, because a third is noise. Referrals become an event on the
path to applying, so referred-versus-cold shows up as a real split in the
funnel.

**Study & Practice.** The biggest thing in the project.

- Practise behavioral answers by talking to an AI interviewer, with a fully
  local voice loop — live captions in the browser, an accurate transcript from
  whisper.cpp afterwards, a local voice for the interviewer. Feedback in three
  layers: delivery metrics computed deterministically with no model at all
  (filler density, words per minute, silences, duration, trended against the
  operator's own baseline), structure scored against the company's real rubric
  where one exists, and a content check that cross-references what was said
  against the corpus. The engine reasons only about what was actually said. It
  never writes an improved version of your story.
- Which problems to practise, by company **and** by skill level — company
  weighting from real reported questions, recency-weighted because pools rotate,
  and skill level from the operator's own attempt record.
- What else to study, derived from **the jobs actually applied to**: system
  design, security, a specific language to brush up on. Not a generic
  curriculum — the aggregate of what those postings require against what the
  corpus can evidence.
- And where and how to study each thing, so the answer is never just "learn
  Kubernetes" but a specific route through it.
- Plus spaced repetition that tolerates a missed week (no growing overdue
  counter, a hard daily cap, most-decayed-first on return), a story bank scored
  against real company criteria, and a "tell me about yourself" builder.

**Week-of and day-of.** The weekly briefing (what is due, new high-match
postings, stale applications, this week's study focus, funnel against cited
published baselines) and the day-of kit: both timezones shown explicitly, this
round's format and criteria, a one-page recap of the operator's own projects and
metrics, the three most relevant stories, and real questions to ask them.

---

## 7. How it is built

**Backend** — Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, httpx,
rapidfuzz. About 10,500 lines.

**Database** — PostgreSQL 16 locally with pgvector; Supabase for deployment. The
`Vector(384)` columns exist and are unused: a reserved seat for semantic search
if it ever earns its weight against the RAM limit.

**Frontend** — React 18, Vite, TypeScript, Tailwind v3. About 4,300 lines. No
router yet, no client-side data layer; both are being added as the page count
grows.

**Tests** — 467, running in about two seconds, pinned to a local database so the
suite never runs over the network against production.

**Hard constraint** — an Apple M3 with 8 GB of RAM. This is why there is no
torch and no sentence-transformers, and why the entire voice loop in part 5 has
to be local and light.

**LLM** — Gemini's free tier, behind a provider interface with a rule-based
fallback for every call, so the app works offline and never hard-depends on
quota. Not built yet; it is the next thing.

### The data model, in one paragraph

Everything personal reads and writes the **corpus** (`corpus_facts`,
`corpus_stories`) and appends to the **event log** (`events`, append-only, with
`occurred_at` separate from `recorded_at` because you log things days after they
happen). Modules never call each other's internals — they go through the corpus
and the log. Shared tables (postings, companies, source health, reported
questions) carry no `user_id`; personal tables carry a nullable one defaulted to
a single operator. That split is what makes multi-user later a config change
rather than a rewrite.

Two modelling decisions worth knowing because they were both learned the hard
way. Company **selectivity** and "I want to work here" are separate tables:
`companies.tier` originally stored both, so marking Jane Street a target
demoted it out of the Reach lane. And `role_family` is a string column rather
than a database enum, so the taxonomy can grow without an `ALTER TYPE` every
time a new major shows up.

---

## 8. The design

**Light "lighthouse" palette.** A cream page, white cards, one navy ramp
carrying structure and type, and a single orange — `beacon` — that is
deliberately rationed. Orange marks the primary action, the live figure, and
real gaps. If a fourth thing starts using it, none of them read as important any
more. The navy masthead is the only dark band on the page.

**Terms are flat with a coloured left rule, not pills.** There are routinely
thirty on screen and thirty rounded outlines read as decoration. The rule colour
carries the bucket, so the list needs no legend.

**Filters are plain text until selected.** Eighteen bordered pills were louder
than the postings they filter.

**The posting window is centred, not a side drawer.** It is a reading surface
meant to replace opening the job site in another tab.

One recurring hazard worth writing down: an undefined Tailwind utility is
*silently dropped* rather than erroring. `mist-500` was used 34 times without
being defined, and `font-600` 49 times — which meant nothing in the app had ever
actually been bold, for weeks, unnoticed. After any token change, grep `.ts` as
well as `.tsx`, and check a computed style in the browser rather than trusting
the diff.

---

## 9. The pages, and how they are used

Four pages today, reached from a navy masthead that also carries live cycle
counts, a source-health dot, and the refresh control.

### The masthead

Always visible. On the left, the name. In the middle, the count of live postings
per applyable cycle — "Fall 2026 · 510", "Summer 2027 · 117" — pulled from the
database, not hard-coded, so it moves as the season turns. On the right, a
source-health dot that is quiet when all sources succeeded and marked when one
is quarantined, and a refresh button that kicks off a background ingest and
shows elapsed seconds while it runs.

The refresh button exists because ingestion takes about 45 seconds and a spinner
with no elapsed time reads as broken.

### Discover — the daily surface

**This is the page the operator opens every day.** The job is to answer "what is
worth an hour of my time today", and everything on it is arranged around that.

**The filter bar** sits under the masthead in two rows. The first row is role
families, all fourteen of them, covering every major rather than just software.
The second row is everything else: internship or new-grad, the four seasons,
sponsorship, remote, a state box, how recently it was posted, full-descriptions-
only, and a search box for a title or company.

Sponsorship and location are deliberately first-class rather than buried in a
menu. A posting the operator cannot legally take is worse than no posting,
because it costs attention before it costs an application. The three sponsorship
options are named the way the posting means them — "Sponsors", "No sponsorship",
"Citizens only" — rather than being collapsed into a single "eligible for me"
toggle, which would hide the posting's own claim behind an inference about the
operator.

**The three lanes** are the main body: Reach, Target, Safety, side by side, each
titled under a full-width rule in its lane colour with a suggested weekly quota.
The split exists because a single ranked list quietly buries ambitious targets
and produces a season of nothing but safe applications. Lane assignment comes
from match score crossed with company selectivity, and the reason is shown.

**A posting card** is dense but scannable. Title and company at the top, and —
if it is already on the board — the stage it is at, because "have I applied to
this?" is the one question a tool should never make you answer from memory. Then
the match meter, which is muted rather than confident when the evidence is thin.
Then the top few real gaps as flat rule-marked terms. Then a hairline, and below
it the metadata that is context rather than another thing to look at: the cycle
and how it was resolved, sponsorship if it matters, location, age, and "4 lists"
when the posting was corroborated across sources.

**Clicking a card opens the posting window**, centred over the page. This is the
piece meant to replace opening the job site in another tab and scrolling two
thousand words for the six facts that matter.

In order: title and company; a row of chips for the cycle, how the cycle was
resolved, locations, sponsorship and age; the exact text that resolved the term,
so the operator can check it; an eligibility banner if — and only if — the
posting actually states a graduation window; then the primary action.

The action row is "Open application" next to the track controls. Untracked,
those are two buttons and a date: **Save** and **I applied** are different
facts, and the second is dated because it seeds every wait-time figure the
funnel will ever report. The date defaults to today and can be moved back,
because applications get logged days after they were sent as often as not.
Already tracked, the buttons are gone and the window shows the real stage, how
long it has been quiet, and only the transitions that make sense from there.

Below the fold: **the posting in facts** — pay, working pattern, length,
deadline, GPA floor, named interview stages, each with the sentence it was
lifted from, because a regex over free prose is wrong often enough that a figure
the reader cannot check is worse than none. Then **the match**, with the meter,
a plain-words summary, and the three term buckets. Then **tailoring**, where the
operator can paste the resume they are about to send and get required-versus-
preferred, hard knockouts, and per-item advice. Then the **ghost checklist**,
then **where it was seen**, then the original description, kept available for
when the parser missed something.

### Applications — the board

Four columns: Saved, Applied, Assessment, Interviewing, with closed applications
folded away behind a count.

**It is not a draggable kanban, on purpose.** Dragging implies you choose the
stage. You don't — the employer does — and what the operator is actually doing
is recording something that already happened, on a date. So the interaction is
"log what happened, on this date", and the grouping follows from that.

Each card shows the role, the company, and the ghosting line when there is one:
"31 days since you applied, no response". That line is the entire ghosting
feature — a subtraction between two real dates, never a probability. It is
measured from the last *employer* signal, so adding your own note does not reset
the clock, and it stays silent on day zero, because a true-but-useless line on
every fresh row trains you to ignore the one that matters at day 40. Past thirty
days it turns orange.

Expanding a card shows the dated timeline. Below it, a date box and the
transitions that are valid from where the row actually is — you cannot log an
offer on something you never applied to. Setbacks are there and rendered
quieter, but never hidden: a rejection is as real a fact as an offer, and the
funnel needs it.

Above the columns sits **the funnel**: stage counts, conversions each shown as
"3 of 12 (25%)" with both numbers, and observed wait times as medians with the
sample size and range. Under ten applications it refuses to show a percentage
and says so.

### My corpus — the spine

Everything personal lives here, and every other feature reads it.

**Coverage** leads the page: over a stated sample of postings that carry a real
description, how many the corpus reaches and how many it does not, plus the most
in-demand terms nothing in the corpus evidences. The sample is always stated
next to the numbers. Gaps are restricted to recognised skill vocabulary —
without that filter the top gaps come back as "engineer", "software",
"technology", which is noise dressed as insight.

**The fact list** groups by type — project, experience, skill, achievement,
education. What makes this more than a CRUD form is that **every fact shows what
it is actually worth**: the terms it contributes, how many live postings mention
each, and how many postings *no other fact reaches*. On the seeded corpus this
immediately showed that the standalone Go, React and TypeScript skill entries
added no coverage the two project entries did not already provide.

**Resume import** takes a PDF, extracts draft facts, and shows them for review.
Nothing is ever saved automatically — extraction and commitment are two separate
API calls, which is the zero-fabrication rule expressed as an interface rather
than a convention.

**Setup** holds the student profile (school, major, degree level, graduation
term, internships completed — counts, never years of experience), target
companies, and constraints. The major field previews live: typing "Finance"
shows *Finance · Business · Quant · Data* before you save, and an unrecognised
major returns nothing rather than guessing.

### Résumé check — the one everyone tries first

Upload a PDF and get back what an ATS actually sees.

**The parse preview is the centrepiece**: the resume as laid out, beside the
resume as a naive parser extracts it. When a two-column layout scrambles, the
operator *sees* the scramble instead of reading a warning about it. Below that,
findings ranked worst-first, each with a concrete fix — contact details in the
header region, non-standard section headings, decorative fonts, bullet glyphs
that get dropped, a PDF that is secretly an image.

Nothing is stored. The file is written to a temp path, analysed, and deleted.

### Where the new pages go

Part 3's company intelligence adds a **company page** — process, rubric, when
their cycle opens, real wait times, whether they actually sponsor, real pay
bands, and specific current details worth mentioning — and a job-intelligence
panel inside the posting window. Part 4 adds **contacts**. Part 5 adds a
**study plan** and a **mock session**. Part 6 adds the **briefing** and the
**day-of kit**.

That is why routing is being added now, at four pages, rather than at twelve.

---

## 10. Working on it

```bash
# backend
.venv/bin/uvicorn lighthouse.api:app --app-dir backend --port 8077 --reload

# frontend
cd web && npm install && npm run dev        # :5173, expects the API on :8077

# CLI, no server needed
PYTHONPATH=backend .venv/bin/python -m lighthouse.cli ingest --max-tier 3
PYTHONPATH=backend .venv/bin/python -m lighthouse.cli discover --role quant
PYTHONPATH=backend .venv/bin/python -m lighthouse.cli sources

# checks
.venv/bin/pytest backend/tests -q
.venv/bin/ruff check backend
cd backend && ../.venv/bin/alembic upgrade head
```

There is a `Makefile` with `install / dev / test / lint / fmt / migrate /
db-reset`. Config is env vars prefixed `LIGHTHOUSE_`; the defaults work offline.

**Three things to know before changing anything.**

Bugs in this project are found by running against live data, not by reading
code. Multi-table attribution, location merging, idempotency, boilerplate
pollution and score compression were every one of them found by hitting the real
database and the real feeds. The design was wrong and the data said so.

`docs/KNOWN_GAPS.md` is the parking lot, and keeping it current is part of the
job. A narrow edge case found mid-feature gets written down rather than chased —
that is how a session ends with one finished module instead of three unfinished
ones. Every entry states the problem, why it happens, and how to fix it. But
**anything that breaks a feature is a bug, not a gap**: a defect that records
wrong data or produces a wrong number gets fixed on the spot however small it
looks. Two entries were filed there wrongly and had to be pulled back out, and
one of them would have silently corrupted every wait-time figure in the app.

`docs/FRONTEND_NOTES.md` is the same idea for design work, and it has a
"settled" section recording decisions that should not be relitigated.

---

## 11. Deliberate decisions people try to reverse

Recorded so nobody spends an afternoon "fixing" one of them.

- **Overlapping phrases are double-counted.** "supply chain management" registers
  as both itself and "supply chain". One pattern per phrase, specifically to
  allow it — a single combined alternation would let the longest match swallow
  the shorter one and silently change every score.
- **The `Vector(384)` columns are unused.** Not dead code. A reserved seat.
- **Conversions are measured from Applied, not between consecutive stages.**
  Real pipelines skip stages; consecutive-pair rates assume they do not.
- **Tier 3 is opt-in per company**, not a blanket crawl. Polite, and it avoids
  thousands of irrelevant requests.
- **No authentication.** Single-user by design for now. The `user_id` columns are
  what make multi-user a config change later.
- **Deployment work is parked** until the product is whole. Batching the ingest
  writes, precomputing the market index and adding auth are all real and all
  correctly deferred — none of them change what the product does.
