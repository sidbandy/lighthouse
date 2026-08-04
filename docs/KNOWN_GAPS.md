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

### `D. E. Shaw` misses its selectivity tier — `misleading`

`canonical_company("D. E. Shaw")` returns `d e shaw` (single letters split on
the periods), but `SEED_TIERS` in `discover/lanes.py` keys on `de shaw`. The
lookup misses, selectivity falls back to the mid default of 2, and an elite
quant firm can land in the Target lane labelled "a realistic match at a
realistic bar" — the exact failure mode the tier/target split was built to
prevent.

**Fix:** either add `"d e shaw"` as a second key in `SEED_TIERS`, or collapse
runs of single letters in `canonical_company` (`d e shaw` → `de shaw`). The
second is more general and would also catch `J. P. Morgan`, but it risks
merging genuinely distinct short names, so the first is the safe move.

### `IMC` and `IMC Trading` are two company rows — `incomplete`

Dedup blocks on `canonical_name`, and neither string is reachable from the other
by the current normalisation. Postings split across both rows, so "seen on N
lists" undercounts and either row can miss a seed tier.

This is a *conscious* trade — `models.py` says it would rather keep two rows
than wrongly merge two real companies — so it is not a bug so much as a known
cost. **Fix, when it starts to bite:** a small alias table mapping known
variants to one canonical name, populated by hand for the companies that
actually matter. Do not attempt fuzzy company merging; that is how "Meta" and
"Meta Materials" become one row.

### Selectivity seed coverage is thin — `misleading`

`SEED_TIERS` is ~40 hand-maintained entries. Genuinely elite firms outside it
(Five Rings Capital, Radix, most of consulting and banking) get the mid default
and can appear in Target. Verified live: Five Rings Capital sits in Target at
selectivity 2.

**Fix:** a pass with a real list once the Companies module exists. The table is
deliberately small and legible rather than exhaustive, so this is expansion, not
redesign. It belongs with Company Intelligence, which will have the data.

---

## Vocabulary and text analysis

### Terms always render lowercase — `cosmetic`

`tokenize_with_surface` lowercases before tokenising, so the surface form keeps
inflection but never capitalisation. The UI shows "kubernetes", "aws", "c++"
where a human would write "Kubernetes", "AWS", "C++".

**Fix:** a display-casing map over the curated vocabulary (`{"aws": "AWS",
"kubernetes": "Kubernetes", …}`), consulted only at render time in
`TermProfile.display`. Do not change the tokeniser — the lowercase stem is the
correct comparison key and changing it would break every count.

---

## Corpus coverage

### The gap list can starve — `incomplete`

`coverage.analyse` draws candidates from `in_demand(limit=gap_limit * 6)` and
then filters out everything the corpus already evidences. A well-covered corpus
that evidences more than five-sixths of the top terms returns fewer gaps than
asked for, while real gaps sit just below the window.

The 6× multiplier is a cost guard, not a considered limit.

**Fix:** widen the window until `gap_limit` survivors are found, or filter first
and take `gap_limit` from the full ranking. The full ranking is a few thousand
entries and already in memory, so the second is cheap and simply correct.

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

### Deleted applications leave their events behind — `incomplete`

`events` has no foreign key to `applications` — deliberately, since the log is
append-only and must outlive the entities it describes. But `DELETE
/api/applications/{id}` removes the application row and leaves its events
orphaned. Verified live: 15 application events against 3 applications.

They are harmless today (`get_or_create` mints a fresh id, so old events can
never re-attach to a new application for the same posting) but they accumulate
and will skew any future "how much have I logged" statistic.

**Fix:** either delete the matching events in the untrack endpoint — acceptable,
since untracking means "this was a mistake, forget it" — or add a
`deleted` tombstone event and filter the log. Prefer the first; the second is
the kind of purity that costs more than it returns for a single-user tool.

### `Application.notes` and `resume_version_id` are never written — `incomplete`

Both columns exist on the model and are plumbed all the way through
`ApplicationState` and the API response, and nothing sets either. Resume-version
tracking is a stated Track goal (HANDOFF §10) that is genuinely not built yet;
free-text notes have no UI.

**Fix:** notes need a field on the application card and a `PATCH
/api/applications/{id}` endpoint. Resume versions need the `ResumeVersion` model
wired to the résumé check flow first — logging *which* résumé got which outcome
is most of the value of the funnel, so this is roadmap, not polish.

### The drawer does not know a posting is already tracked — `misleading`

`TrackActions` always renders "Save" and "I applied" regardless of whether the
posting is already on the board. Clicking again is harmless — `get_or_create` is
idempotent and returns the existing row — but the operator gets no signal that
they already applied, which on a 200-row board is exactly the mistake they need
protecting from.

**Fix:** include the current application stage on `PostingDetail` (one join), and
render the existing stage plus the next valid transitions instead of the save
buttons. The same field would let Discover mark already-tracked postings, which
is the more valuable half.

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

Measured over 400 real descriptions: compensation 30%, length 20%, working
pattern 19%, interview process 10%, deadline 6%, GPA 4%, responsibilities 77%.
The low numbers are mostly postings that genuinely say nothing (`is_thin` exists
to surface exactly that), but deadline and GPA are also the weakest patterns.

**Fix:** widen `_DEADLINE_RE` to catch bare dates near "apply" and month-name
formats; `_GPA_RE` misses "3.0 or above" and "minimum cumulative average". Both
are contained regex work with a 400-posting corpus already available to measure
against — re-run the counting script in the commit for this feature.

### Annualised intern salaries read as absurd — `misleading`

Quant firms quote interns an annualised base ("Base Salary: $250,000") which the
brief reports verbatim as "$250,000 per year" for a ten-week internship. The
extraction is correct and the evidence tooltip shows the source sentence, but
the number is easy to misread.

**Fix:** when a duration is also extracted and the pay is annual, show the
prorated figure alongside — "$250,000/yr · ~$48k over 10 weeks". Do not replace
the stated figure; add to it.

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
