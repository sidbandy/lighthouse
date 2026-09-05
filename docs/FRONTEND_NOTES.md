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

### Saved views / filter presets

The filter bar resets on reload, and there are now ten filters rather than three,
so rebuilding a query costs more than it used to. Someone applying seriously runs
the same three or four repeatedly ("SWE + Summer 2027 + full descriptions").

Routing is in place, so the natural home is the query string rather than
`localStorage` — that makes a view shareable and survives reload for free. Move
to the profile once multi-user lands.

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

**The masthead is fixed; the dense pages are not yet audited.** The header used
to lay seven nav links, the cycle chips and two controls in one non-wrapping
row, which needed ~950px and made the whole page scroll sideways at 390px --
measured at 1,079px of content in a 390px viewport. Below `lg` the links now
move into a menu, and the cycle counts and refresh go with them.

Every route now fits 390px with no horizontal scroll, checked in a real
browser. What has *not* been done is reading the dense pages at that width for
whether they are pleasant rather than merely contained: the three Discover
lanes stack into one long column, and the application board's columns will do
the same. Worth an actual look on a phone before the next round of applying.

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
- **Routing is `react-router`, and the posting window has its own URL**
  (`/discover/:postingId`). Added at four pages rather than at twelve, because
  the company page, contact pages, study plan, mock session and day-of kit all
  need one. A deployed build needs the host to rewrite unknown paths to
  `index.html`, or a reload on `/corpus` will 404.
