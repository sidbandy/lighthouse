"""Recruiting cycles, and which of them are still worth applying to.

The problem this solves: every popular internship list is organised around a
single Summer cycle, so a tool built around one of them quietly goes stale.
Lighthouse instead asks "given today, which cycles can the operator still apply
to?" and lets that drive ingestion filters and UI defaults. Nothing needs
editing when the calendar rolls over.

A cycle stops being applyable at roughly the point it begins -- you cannot
apply to a Summer 2026 internship in July 2026, because it is already running.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from ..core.models import Season

# Month each cycle typically begins. Winter and Spring genuinely overlap in the
# US academic calendar (both start in January); the tie is broken by
# ``_SEASON_ORDER`` so ordering stays stable rather than arbitrary.
_START_MONTH: dict[Season, int] = {
    Season.WINTER: 1,
    Season.SPRING: 1,
    Season.SUMMER: 5,
    Season.FALL: 9,
}

_SEASON_ORDER: dict[Season, int] = {
    Season.WINTER: 0,
    Season.SPRING: 1,
    Season.SUMMER: 2,
    Season.FALL: 3,
}

_SEASON_WORDS: dict[str, Season] = {
    "spring": Season.SPRING,
    "summer": Season.SUMMER,
    "fall": Season.FALL,
    "autumn": Season.FALL,
    "winter": Season.WINTER,
}

# "Summer 2027", "summer '27", "Fall2026"
_TERM_RE = re.compile(
    r"\b(spring|summer|fall|autumn|winter)\s*'?\s*(\d{2}|\d{4})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=False)
class Cycle:
    """A single recruiting cycle, e.g. Summer 2027."""

    season: Season
    year: int

    @property
    def start_date(self) -> date:
        return date(self.year, _START_MONTH[self.season], 1)

    @property
    def label(self) -> str:
        return f"{self.season.value.capitalize()} {self.year}"

    @property
    def sort_key(self) -> tuple[date, int]:
        return (self.start_date, _SEASON_ORDER[self.season])

    def is_applyable_on(self, today: date) -> bool:
        """True while the cycle has not yet begun."""
        return today < self.start_date

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.label


def normalize_year(raw: int | str) -> int:
    """Expand a two-digit year. ``27`` -> ``2027``."""
    value = int(raw)
    return 2000 + value if value < 100 else value


def parse_cycle(text: str | None) -> Cycle | None:
    """Extract a cycle from free text, or ``None`` if there isn't one.

    Handles the term strings aggregator feeds use ("Summer 2026") as well as
    looser text found in titles ("SWE Intern - Fall '26"). Deliberately returns
    ``None`` rather than guessing: an unresolved term is shown as "unknown" and
    is filterable, which is more useful than a wrong cycle.
    """
    if not text:
        return None
    match = _TERM_RE.search(text)
    if not match:
        return None
    season = _SEASON_WORDS[match.group(1).lower()]
    return Cycle(season=season, year=normalize_year(match.group(2)))


def applyable_cycles(today: date, horizon_months: int = 24) -> list[Cycle]:
    """Cycles the operator can still apply to, soonest first.

    ``horizon_months`` trims the far future: a Summer 2029 posting surfacing
    today is noise, not opportunity.

    From 2026-07 this yields Fall 2026, Winter 2027, Spring 2027, Summer 2027,
    Fall 2027 -- i.e. the off-cycle roles that are open right now *and* the next
    main Summer cycle.
    """
    horizon = _add_months(today, horizon_months)
    cycles = [
        cycle
        for year in range(today.year, today.year + (horizon_months // 12) + 2)
        for season in Season
        if (cycle := Cycle(season, year)).is_applyable_on(today) and cycle.start_date <= horizon
    ]
    return sorted(cycles, key=lambda c: c.sort_key)


def next_cycle_of(season: Season, today: date) -> Cycle:
    """The soonest still-applyable cycle for a given season."""
    candidate = Cycle(season, today.year)
    if not candidate.is_applyable_on(today):
        candidate = Cycle(season, today.year + 1)
    return candidate


def is_applyable(cycle: Cycle | None, today: date, horizon_months: int = 24) -> bool:
    """Whether a posting's cycle is one we should still surface.

    Postings whose cycle could not be resolved (``None``) are *kept*: dropping
    them would silently hide real roles, so they surface flagged as "term
    unknown" for the operator to judge.
    """
    if cycle is None:
        return True
    return cycle.is_applyable_on(today) and cycle.start_date <= _add_months(today, horizon_months)


def _add_months(anchor: date, months: int) -> date:
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)
