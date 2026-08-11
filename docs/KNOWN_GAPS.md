# Known gaps

Everything real, small, and deliberately not fixed yet. Nothing here breaks the
app. Each entry is something found while running against live data, judged not
worth interrupting the build for, and written down so it is not rediscovered
from scratch later.

**How to use this file**

- **Add to it rather than fixing inline**, unless the issue actually blocks the
  thing being built. Chasing every edge case mid-feature is how a session ends
  with three half-finished modules.
- **Every entry states the problem, why it happens, and how to fix it.** An
  entry that only says "X is weird" costs a future session the same
  investigation that produced it.
- **Delete entries when they are fixed.** Git history is the record of what was
  fixed; this file is the record of what is *not*. A stale entry is worse than
  no entry, because it sends someone to look at working code.
- **Anything that breaks a feature gets fixed, not parked.** This file is for
  things that do not affect the app working — narrow edge cases, and
  nice-to-haves. If a defect makes a shipped feature record wrong data, produce
  a wrong number, or mislead a decision, it is not a gap; stop and fix it. Two
  entries were wrongly filed here and had to be pulled back out (the board
  stamping every stage as "now", and synonym pairs splitting one skill into
  two) — that is the mistake this rule exists to prevent.
- **Severity** is about consequence, not effort. Only the bottom three belong
  in this file:
  - `wrong` — produces an incorrect number or claim the operator might act on.
    **Does not belong here. Fix it.**
  - `misleading` — technically true, reads as something else.
  - `incomplete` — a real capability is missing or half-wired.
  - `cosmetic` — looks or reads badly, changes no decision.

---

## Entity resolution

### Selectivity seed coverage is still hand-maintained — `misleading`

`SEED_TIERS` is now ~90 entries covering the companies that actually appear in
the ingested data, but it remains a hand list. A genuinely elite firm outside it
gets the mid default and can appear in Target.

**Fix:** a real pass once Company Intelligence exists — it will have H1B filing
volumes, posting counts and process data, all of which bear on how hard a company
is to get into. Expansion, not redesign.

### Descriptions skew toward selective companies — `incomplete`

Only Tier 3 (direct ATS boards) carries full descriptions, and the seed list was
originally all elite and high-tier firms. Measured over a 400-posting scored
slice: 141 elite, 137 high, 121 mid, **1 accessible**. So the postings the
operator could evaluate best were the ones they were least likely to get.

Ten mid-tier boards were added and verified live, which helps but does not close
it: the genuinely accessible end of the market (IBM, the defence primes, the
large IT services firms) is almost entirely on **Workday**, which is POST-based
and Akamai-gated and has no connector.

**Fix:** a Workday connector, or Tier 4 aggregators (JobSpy/Indeed) which do
carry descriptions for those employers. Either is a real piece of work. Until
then the Safety lane is populated from title-only rows and says so.

### Near-duplicate reqs from one employer crowd a lane — `cosmetic`

Red Bull posts ~730 near-identical "Sales Trainee" rows across locations, and
dedup correctly keeps them apart — different URLs, different reqs, genuinely
different jobs. Two of them adjacent in a lane still reads as a bug to anyone
looking at it.

**Fix:** collapse runs of the same (company, normalised title) into one card
with a location count, expandable. Do *not* merge them in the data; they are
separate applications.

---

## Corpus coverage

### "Reach" is a deliberately weak bar — `misleading`

`FactContribution.reach` counts a sampled posting if it mentions **any** term the
fact contributes — a single mention of "python" is enough. The UI states the
definition exactly ("postings mention its terms"), and the number is honest, but
a reader skimming will take it as "postings I'd be a fit for".

**Fix (if it proves misleading in use):** offer a second, stricter count —
postings where the fact's terms are *emphasised* (`core_count` semantics) rather
than merely present — and show both. Do not silently redefine `reach`; the
current number is correct for what it says.

### First coverage build after an ingest is slow — `cosmetic`

`MarketIndex` tokenises every sampled description. At the current 425 postings
that is ~1.1s; at the `MAX_SAMPLE` cap of 1500 it would be ~4s, paid on the
first corpus-page load after any ingest, because the cache key includes the
posting count and latest sighting.

**Fix:** warm the index in a background thread at app startup and at the end of
`run_ingest`. The cache already exists and is keyed correctly; this only moves
when the cost is paid.

---

## Track: applications

### Silence is measured in server-local days — `cosmetic`

`days_silent` compares `datetime.now(UTC).date()` against the event date. Near
midnight, or for an operator far from UTC, the count can be off by one.

**Fix:** take the operator's timezone from `OperatorProfile` (the table exists;
the column does not) and compute the reference date in it. Not worth doing until
the deadline calendar in Company Intelligence needs real timezone handling
anyway — do both together.

---

## Discover: the posting brief

### Extraction coverage is uneven by field — `incomplete`

Re-measured over 502 real descriptions: responsibilities 79%, compensation 30%,
working pattern 20%, length 19%, interview process 9%, deadline 6.4%, GPA 5.4%.
The low numbers are mostly postings that genuinely say nothing — `is_thin` exists
to surface exactly that — and deadline and GPA are now *correct* at those rates
rather than padded with false positives.

**Fix, if it is worth more:** `_DEADLINE_RE` still only catches phrasings that
name an application explicitly, which is the right trade (see the "tight
deadlines" false positive it used to produce). Interview process at 9% is the
weakest genuinely-improvable field. Measure any change over the same 502
descriptions before and after; do not accept a coverage gain without reading a
sample of what it newly matched.

## Deployment

### CORS only allows the Vite dev origin — `incomplete`

`api.py` pins `allow_origins` to `http://localhost:5173` and its 127.0.0.1
equivalent. Correct and tight for local development, and it will reject the
deployed frontend the moment one exists — the failure looks like "could not
reach the API" in the browser with the API plainly healthy, which is a
half-hour of confusion if you have not seen it before.

**Fix:** read the allowed origins from settings so the deploy can add its own,
keeping the local defaults. Belongs with the deployment work, not before it.

### Ingest is far too slow against a remote database — `incomplete`

`pipeline.py` persists postings through the ORM row by row. Against local
Postgres a full tier-1-2 run finishes in about 45 seconds. Against Supabase over
the network the same run was still going after 20 minutes, because every insert
and update is its own round trip and there are ~27k postings plus ~37k source
sightings.

This matters for deployment, not just for patience: `.github/workflows/ingest.yml`
has a 30-minute timeout and runs against Supabase. **A scheduled ingest will
likely time out as written.**

**Fix:** batch the writes. `session.bulk_insert_mappings` / `bulk_update_mappings`,
or a Postgres `INSERT ... ON CONFLICT DO UPDATE` built from the deduped rows,
turns tens of thousands of round trips into tens. The dedup logic already
produces a clean list of rows to write, so this is a change to the persistence
step only. Measure against Supabase, not locally — locally it is fast enough to
hide the problem entirely.

**Until then:** run ingest locally and treat the local database as the source of
truth, or raise the workflow timeout and accept a long run.

## Schema

### Models and database have drifted on three tables — `incomplete`

Autogenerate proposed, and this session deliberately did not take: NOT NULL on
`operator_profiles.created_at`/`updated_at` and `operator_targets.created_at`, a
unique constraint on `operator_profiles.user_id` swapped for a unique index, and
an index on `postings.role_family`. All real, none of it part of the change that
surfaced it.

It was left out because a migration that quietly alters unrelated tables is how
a rollback stops being safe. **Fix:** its own revision, reviewed by hand, with
the `postings.role_family` index checked against the query plan first — that
table is large and the index may or may not earn its write cost.

## Networking

### Draft hooks are postings, not specificity hooks — `incomplete`

`drafts._company_hook` lifts "the {title} opening in {location}" from the
company's most recent posting. It is checkable and true, which is the bar, but
it is thinner than the spec's §4.5 specificity hooks — a recent launch or an
engineering blog post is a much better reason to have written.

**Fix:** it becomes a one-line swap once Company Intelligence populates
`specificity_hooks`. The seam is already there.

### School matching is exact, so "UT Austin" ≠ "University of Texas" — `misleading`

`alumni.is_alumni` compares the strings the operator typed. Two spellings of one
school will not match, and the contact silently loses its alumni marker.

**Fix:** normalise through a small alias list, the same shape as the company
aliases. Do **not** fuzzy-match: a wrong "we're alumni" line goes into a real
message to a real person, which is worse than a missed one the operator can fix
by editing a field.

## Study and practice

### `reported_questions` is empty, so the company delta has nothing to say — `incomplete`

The table, the recency weighting and the leverage sentence all exist and are
tested. There are no rows, so `company_delta` returns `coverage_quality: none`
and says so — which is correct behaviour, not a bug, but it means the "core
layer plus company delta" structure is currently core layer only.

**Fix:** Company Intelligence's population pipeline (Reddit + LeetCode through
the operator review queue). Nothing in this module changes when the data
arrives; it is already reading the table.

### The problem catalogue is 45 problems, hand-maintained — `incomplete`

Enough to enter every pattern and to drive the SRS, not enough for months of
practice. Deliberate — a list of four hundred is a list nobody starts — but a
serious user will exhaust a pattern's catalogued problems and see it drop out of
the suggestions.

**Fix:** widen it per pattern as the gap shows up, or link out to the full
NeetCode list per pattern once exhausted. Do not bulk-import a thousand problems;
the small curated set is the feature.

### Topic triggers are substring matches — `misleading`

`curriculum` matches trigger phrases against the posting text. Specific phrases
were chosen after a live run showed "training" in an aerospace posting
recommending an ML course, and there is a test pinning the ambiguous words out.
It is still substring matching, so a posting saying "no system design experience
required" would count as asking for system design.

**Fix:** if it bites, check for a negation window before the match. Do not
switch to a model for this — the current rule is legible and its failures are
inspectable, which a classifier's would not be.

## Data hygiene

### The seeded corpus is still fake — `incomplete` (data, not code)

`corpus_facts` holds 12 facts from a *test* résumé (Cloudify / Ledger / UT CS
2028) used during development, not the operator's real history. Every match
score, lane assignment and coverage figure in the app is currently computed
against a stranger.

**Fix:** delete them and import a real résumé through the corpus page, which now
exists for exactly this. Until then, treat every number on screen as a smoke
test rather than as advice.

---

## Not gaps — deliberate, recorded so they are not "fixed" by mistake

- **Overlapping phrases are double-counted.** "supply chain management" registers
  as both itself and "supply chain". `extract_phrases` runs one pattern per
  phrase specifically to allow this; a single combined alternation would let the
  longest match swallow the shorter one and silently change every score.
- **`Vector(384)` columns are unused.** Kept so semantic search can be added if
  it ever earns its weight against the 8 GB RAM limit. Not dead code — a
  reserved seat.
- **Conversions are measured from Applied, not between consecutive stages.** Real
  pipelines skip stages; consecutive-pair rates assume they do not.
- **No authentication.** Single-user by design. The `user_id` columns are what
  make multi-user a config change later.
