"""Working out which recruiting cycle a posting belongs to.

Only ~5% of job titles name their season, so for most rows the cycle has to be
worked out from whatever else is available. This module runs an ordered cascade
of rules and records *which rule fired* along with the text that triggered it.

That is deliberate. A confidence score would be an invented number; "term from
title" or "inferred from 'May 2027 - August 2027'" is evidence the operator can
check. When no rule fires the posting is labelled ``unknown`` and stays
filterable -- it is never guessed at.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from ..core.models import (
    TERM_RULE_DESCRIPTION_DATES,
    TERM_RULE_ELIGIBILITY,
    TERM_RULE_EXPLICIT_FIELD,
    TERM_RULE_TITLE,
    TERM_RULE_UNKNOWN,
    Season,
)
from .seasons import Cycle, normalize_year, parse_cycle

_MONTHS: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip

# Which cycle a programme starting in a given month belongs to. Co-op postings
# overwhelmingly describe themselves by start month, so this is the mapping
# that matters in practice.
_START_MONTH_SEASON: dict[int, Season] = {
    1: Season.SPRING, 2: Season.SPRING, 3: Season.SPRING, 4: Season.SPRING,
    5: Season.SUMMER, 6: Season.SUMMER, 7: Season.SUMMER, 8: Season.SUMMER,
    9: Season.FALL, 10: Season.FALL, 11: Season.FALL,
    12: Season.WINTER,
}  # fmt: skip

_MONTH_ALT = "|".join(_MONTHS)

# "May 2027 - August 2027", "May - Aug 2027", "January to April 2027"
_RANGE_RE = re.compile(
    rf"\b({_MONTH_ALT})[a-z]*\.?\s*(\d{{4}})?\s*(?:-|--|–|—|to|through|until)\s*"
    rf"({_MONTH_ALT})[a-z]*\.?\s*(\d{{4}})\b",
    re.IGNORECASE,
)

# "starting May 2027", "begins in January 2027", "start date: June 2027"
_START_RE = re.compile(
    rf"\b(?:start(?:s|ing)?|begin(?:s|ning)?|commenc\w+)\b[^.\n]{{0,30}}?"
    rf"\b({_MONTH_ALT})[a-z]*\.?\s*,?\s*(\d{{4}})\b",
    re.IGNORECASE,
)

# "graduating in 2028", "expected graduation: December 2027", "class of 2028"
_GRAD_RE = re.compile(
    r"\b(?:graduat\w+|class of|degree completion)\b[^.\n]{0,40}?\b(20\d{2})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TermResolution:
    """The outcome of the cascade: a cycle, the rule that found it, and why."""

    cycle: Cycle | None
    rule: str
    evidence: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.cycle is not None


UNRESOLVED = TermResolution(cycle=None, rule=TERM_RULE_UNKNOWN, evidence=None)


def _snippet(text: str, match: re.Match, width: int = 60) -> str:
    """A short quote around a match, for showing the operator the evidence."""
    start = max(0, match.start() - width // 3)
    end = min(len(text), match.end() + width // 3)
    return " ".join(text[start:end].split())


def _from_explicit(terms: Sequence[str] | None, today: date) -> TermResolution | None:
    """Rule 1: the source already told us.

    Feeds like Simplify carry a ``terms`` array. A posting can legitimately
    carry several ("Summer 2027", "Fall 2027"); we take the soonest one that
    has not already started, because that is the one being recruited for now.
    """
    if not terms:
        return None
    cycles = [c for term in terms if (c := parse_cycle(term))]
    if not cycles:
        return None
    upcoming = [c for c in cycles if c.is_applyable_on(today)] or cycles
    chosen = min(upcoming, key=lambda c: c.sort_key)
    return TermResolution(chosen, TERM_RULE_EXPLICIT_FIELD, chosen.label)


def _from_title(title: str | None, *_: object) -> TermResolution | None:
    """Rule 2: the title names the cycle outright ("SWE Intern, Summer 2027")."""
    cycle = parse_cycle(title)
    if cycle is None:
        return None
    return TermResolution(cycle, TERM_RULE_TITLE, title.strip() if title else None)


def _from_description_dates(description: str | None) -> TermResolution | None:
    """Rule 3: the description states the programme dates.

    Covers both explicit ranges ("May 2027 - August 2027") and a stated start
    ("16-week co-op beginning January 2027"). The start month determines the
    cycle, since that is how co-op postings describe themselves.
    """
    if not description:
        return None

    if match := _RANGE_RE.search(description):
        start_month = _MONTHS[match.group(1)[:3].lower()]
        # A range may only date its end ("May - August 2027"); the start year
        # then equals the end year unless the range wraps a new year.
        end_year = int(match.group(4))
        end_month = _MONTHS[match.group(3)[:3].lower()]
        start_year = int(match.group(2)) if match.group(2) else end_year
        if not match.group(2) and start_month > end_month:
            start_year = end_year - 1
        season = _START_MONTH_SEASON[start_month]
        return TermResolution(
            Cycle(season, start_year), TERM_RULE_DESCRIPTION_DATES, _snippet(description, match)
        )

    if match := _START_RE.search(description):
        month = _MONTHS[match.group(1)[:3].lower()]
        season = _START_MONTH_SEASON[month]
        return TermResolution(
            Cycle(season, int(match.group(2))),
            TERM_RULE_DESCRIPTION_DATES,
            _snippet(description, match),
        )
    return None


def _from_eligibility(description: str | None, today: date) -> TermResolution | None:
    """Rule 4: a graduation requirement implies the cycle.

    "Graduating in 2028" on an internship means the summer *before* that
    graduation -- Summer 2027. Narrow and conservative on purpose: it only
    fires for internships, only for a plausible graduation year, and always
    records the phrase it keyed off so the operator can sanity-check it.
    """
    if not description:
        return None
    match = _GRAD_RE.search(description)
    if not match:
        return None
    grad_year = int(match.group(1))
    if not (today.year <= grad_year <= today.year + 6):
        return None
    return TermResolution(
        Cycle(Season.SUMMER, grad_year - 1), TERM_RULE_ELIGIBILITY, _snippet(description, match)
    )


def resolve_term(
    *,
    title: str | None = None,
    description: str | None = None,
    explicit_terms: Sequence[str] | None = None,
    today: date | None = None,
    infer_from_eligibility: bool = True,
) -> TermResolution:
    """Run the cascade and return the first rule that resolves.

    Order is strict best-evidence-first: what the source stated, then the
    title, then dates in the description, then a graduation requirement.
    """
    today = today or date.today()

    rules: list[Callable[[], TermResolution | None]] = [
        lambda: _from_explicit(explicit_terms, today),
        lambda: _from_title(title),
        lambda: _from_description_dates(description),
    ]
    if infer_from_eligibility:
        rules.append(lambda: _from_eligibility(description, today))

    for rule in rules:
        if (resolution := rule()) is not None:
            return resolution
    return UNRESOLVED


def normalize_term_label(text: str) -> str | None:
    """Canonicalise a raw term string to "Season YYYY", or ``None``.

    Used when comparing terms across feeds that spell them differently
    ("summer '27" vs "Summer 2027").
    """
    cycle = parse_cycle(text)
    return cycle.label if cycle else None


__all__ = [
    "TermResolution",
    "UNRESOLVED",
    "normalize_term_label",
    "normalize_year",
    "resolve_term",
]
