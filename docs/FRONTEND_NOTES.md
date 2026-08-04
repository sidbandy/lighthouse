# Frontend notes

Design and UX work that is **deliberately deferred**. Functionality comes first;
this is where frontend thinking gets parked so it stops competing for time.

Same rules as `KNOWN_GAPS.md`: state the idea and why it matters, delete entries
once they ship, and read the "settled" section before changing something that
looks arbitrary.

---

## Settled — do not relitigate

- **Light theme only, lighthouse palette.** Cream `paper` page, white cards,
  one `navy-*` ramp, `beacon-*` orange. No dark mode; the operator ruled it out
  explicitly.
- **The beacon is rationed.** Orange marks the primary action, the live figure,
  and real gaps. If a third thing starts using it, none of them read as
  important any more.
- **Flat rule-marked terms, not pills.** `.term` uses a coloured left border
  because there are routinely thirty on screen and thirty rounded outlines read
  as decoration. The rule colour carries the bucket so the list needs no legend.
- **Filters are plain text until selected.** Eighteen bordered pills were louder
  than the postings they filter.
- **The posting window is centred, not a side drawer.** It is a reading surface
  meant to replace opening the job site in another tab.
- **Numeric font weights** (`font-600`) are defined in the config. They were
  used for months while undefined, and an undefined Tailwind utility is silently
  dropped — nothing was bold. Same class of bug as `mist-500`. **After any token
  change, grep `*.ts` as well as `*.tsx`, and probe a computed style in the
  browser rather than trusting the diff.**

---

## Worth building, roughly in order of value

### Show tracked state everywhere a posting appears

Right now the drawer always offers "Save" and "I applied" even for something
already on the board, and Discover gives no hint which postings are tracked. On
a list of thousands, "have I already applied to this?" is the question the tool
should never make you answer from memory.

Needs one field on `PostingSummary` (the current stage, or null), which is a
single join. Then: a marker on the card, and the drawer showing the real stage
plus valid transitions instead of the save buttons. **This is the highest-value
frontend item.** Also tracked in `KNOWN_GAPS.md`.

### A date control on every stage transition

The board logs everything as "now". Back-filling a real search — the first thing
anyone does — produces twelve applications all dated today and every wait-time
figure downstream is then wrong. The API already accepts `occurred_at`.

### Saved views / filter presets

The filter bar resets on reload. Someone applying seriously runs the same three
or four queries repeatedly ("SWE + Summer 2027 + full descriptions"). Persist to
`localStorage` first; move to the profile once multi-user lands.

### Keyboard navigation on Discover

`j`/`k` between cards, `Enter` to open, `s` to save, `a` to log applied, `esc` to
close. This is a tool for working through a list quickly, and mousing through
200 postings is the slowest possible way to do it.

### Bulk actions

Select several postings and save them all. Application sprees are how the search
actually happens; one-at-a-time is friction exactly when volume matters.

### Virtualised posting list

The lanes render every posting. Fine at 20 per lane; not fine if the cap is ever
lifted. `@tanstack/react-virtual` is the light option — do not add it before it
is needed.

### Empty and loading states that say something

Several currently say "Loading…". Each should say what is being loaded and why
it is slow when it is (the corpus coverage build is ~1s cold and is the obvious
one).

### Mobile

Untouched. The lanes and the board are both multi-column and will be unusable
on a phone. Probably not worth solving until someone actually wants it, but
worth knowing it does not work rather than discovering it in front of a friend.

---

## Architectural notes for later

- **No client-side data layer.** `api/client.ts` is a thin fetch wrapper and
  every page refetches on mount. Correct for a local single-user app. When
  multi-user lands over the network, revisit — React Query would remove a lot of
  hand-rolled loading state, and the refresh polling already wants it.
- **Types are hand-written** in `api/types.ts` mirroring the Pydantic schemas.
  They have drifted zero times so far because the surface is small, but the
  moment it grows, generate them from the OpenAPI schema FastAPI already serves
  at `/openapi.json`.
- **No router.** `App.tsx` switches on a `view` string, so no deep links and no
  back button. Add `react-router` when a URL needs to be shareable — which is
  the moment friends start using it.
