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

### Selectivity seed coverage is thin, and Safety is empty because of it — `misleading`

`SEED_TIERS` is ~40 hand-maintained entries. Genuinely elite firms outside it
(Five Rings Capital, Radix, most of consulting and banking) get the mid default
and can appear in Target. Verified live: Five Rings Capital sits in Target at
selectivity 2.

Worse than the entry originally recorded: **the Safety lane is structurally
almost always empty.** `assign_lane` requires `selectivity <= 1` for Safety, and
only five companies in the seed table sit at that tier (ibm, oracle, cisco,
dell, accenture). Verified live at the page size the UI actually requests
(`per_lane=20`): Reach 20, Target 19, Safety 0. The three-lane view is the
headline Discover surface and it is currently running on two lanes.

**Fix:** a real selectivity pass once Company Intelligence exists — it will have
H1B filing volumes, posting counts and process data, all of which bear on how
hard a company is to get into. The lane thresholds themselves are *not* the
problem and should not be tuned first: the logic is legible and correct, it is
being fed a table with almost nothing at the accessible end. Do not tune against
the current corpus either, which is still a stranger's (see below) — that would
be fitting to noise.

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
