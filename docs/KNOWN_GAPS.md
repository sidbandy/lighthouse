# Known gaps

Small, real, and deliberately deferred. Nothing here breaks the app — each is a
narrow edge case found while running against live data. They are parked so the
base product gets built first, and batched because most of them are one-line
fixes that are cheaper to do in a single pass than to chase individually.

Add to this file rather than fixing inline, unless the issue is actually
blocking something.

---

## Entity resolution

- **`D. E. Shaw` canonicalizes to `d e shaw`**, but the selectivity seed table
  keys on `de shaw`, so the row misses its elite tier and falls back to the mid
  default. Either normalize single-letter runs or add the variant to
  `SEED_TIERS` in `discover/lanes.py`.
- **`IMC` and `IMC Trading` are two separate company rows.** Dedup blocks on
  `canonical_name`, and neither is a prefix rule away from the other. Same class
  of problem as `Meta` / `Meta Platforms Inc.` — the module docstring already
  says it would rather keep two rows than wrongly merge, so this is a conscious
  trade, not a bug. Revisit if the target list gets noisy.
- **Selectivity seed coverage is thin.** `SEED_TIERS` is ~40 hand-maintained
  entries, so genuinely elite firms outside it (Five Rings Capital, for one) get
  the mid default and can land in the Target lane. The table is deliberately
  small and legible; it wants a pass with a real list of quant/consulting/
  banking firms once the Companies module exists.

## Vocabulary

- **`postgres` and `postgresql` are separate terms** in `TECH_TERMS`, so a
  project saying "Postgres" and a skill fact saying "PostgreSQL" evidence
  different things and neither gets full credit. There is a small family of
  these (`golang`/`go`, `nodejs`/`node.js`, `k8s`/`kubernetes`). Wants an alias
  map in `core/textanalysis.py` collapsing known synonyms to one canonical stem
  — which is also roughly what the deferred Lightcast Skills integration would
  give for free.
- **Term display is always lowercase.** `tokenize_with_surface` lowercases
  before tokenizing, so the surface form preserves inflection but never
  capitalization: the UI shows "kubernetes", never "Kubernetes". Cosmetic. A
  display-casing map over the curated vocabulary would fix it.

## Coverage

- **The corpus gap window can starve.** `coverage.analyse` draws gaps from
  `in_demand(limit=gap_limit * 6)` and then filters out anything the corpus
  already evidences. A well-covered corpus can therefore return fewer gaps than
  asked for while real ones sit further down the ranking. The 6× window is a
  cost guard; make it adaptive if it ever bites.

## Data hygiene

- **`corpus_facts` still holds 12 facts from a test résumé** (Cloudify / Ledger
  / UT CS 2028), not the operator's real history. The corpus page exists to
  replace them. Until it is used, every match score is computed against a
  stranger.
