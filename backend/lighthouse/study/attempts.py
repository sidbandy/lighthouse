"""The per-pattern record, and what to practise next.

The spec proposed a decayed mastery score with a Bayesian prior for cold start.
Both are overruled here by the no-invented-numbers rule, and the substitute is
not a compromise -- it is more useful. "Graph: 2 of 7 clean, last attempt 9 days
ago" tells you what to do. "Graph mastery: 0.34" does not, and it invites you to
trust a number fitted to seven data points.

Recency matters, so it is expressed as *which attempts are shown* rather than as
a decay coefficient: the last few, most recent first, with their dates. A
pattern you nailed three months ago and have not touched reads as exactly that,
without anyone having to pick a half-life.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import PracticeAttempt
from .catalog import PATTERNS, PATTERNS_BY_SLUG, Pattern, Problem, problems_for


class Outcome(StrEnum):
    SOLVED_CLEAN = "solved_clean"
    SOLVED_WITH_HINT = "solved_with_hint"
    SOLVED_OVER_TIME = "solved_over_time"
    FAILED = "failed"


OUTCOME_LABELS: dict[Outcome, str] = {
    Outcome.SOLVED_CLEAN: "Solved clean",
    Outcome.SOLVED_WITH_HINT: "Needed a hint",
    Outcome.SOLVED_OVER_TIME: "Solved, over time",
    Outcome.FAILED: "Did not get it",
}

# How many recent attempts a pattern needs before its record says anything. Two
# attempts is an anecdote; the honest output below that is "not enough yet".
MIN_ATTEMPTS = 3

# The window the record is read over. Attempts older than this are still stored
# -- nothing is deleted -- but they stop counting toward "where am I now",
# because a search runs for months and last spring is not evidence about today.
RECENT_WINDOW = 8


@dataclass(slots=True)
class PatternRecord:
    """One pattern and the operator's actual history with it."""

    pattern: Pattern
    attempts: list[PracticeAttempt] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return self.pattern.slug

    @property
    def recent(self) -> list[PracticeAttempt]:
        return self.attempts[:RECENT_WINDOW]

    @property
    def total(self) -> int:
        return len(self.recent)

    @property
    def clean(self) -> int:
        return sum(1 for a in self.recent if a.outcome == Outcome.SOLVED_CLEAN)

    @property
    def has_enough(self) -> bool:
        return self.total >= MIN_ATTEMPTS

    @property
    def last_attempted(self) -> datetime | None:
        return self.attempts[0].attempted_at if self.attempts else None

    def days_since(self, today: date | None = None) -> int | None:
        last = self.last_attempted
        if last is None:
            return None
        return max(0, ((today or datetime.now(UTC).date()) - last.astimezone(UTC).date()).days)

    def statement(self, today: date | None = None) -> str:
        """The record in one line. Counts and dates only."""
        if self.total == 0:
            return "No attempts yet."
        gap = self.days_since(today)
        when = f", last {gap} day{'s' if gap != 1 else ''} ago" if gap is not None else ""
        if not self.has_enough:
            return (
                f"{self.clean} of {self.total} clean{when} — "
                f"too few to read anything into yet."
            )
        return f"{self.clean} of {self.total} clean{when}."

    @property
    def is_weak(self) -> bool:
        """Fewer than half the recent attempts clean, on a real sample.

        A deliberate threshold rather than a computed one, stated in a single
        place. Below the sample floor a pattern is not weak, it is unmeasured,
        and those are different problems with different answers.
        """
        return self.has_enough and self.clean * 2 < self.total

    @property
    def is_untouched(self) -> bool:
        return self.total == 0


def _operator_id() -> uuid.UUID:
    from ..core.config import get_settings

    return get_settings().operator_id


def log_attempt(
    session: Session,
    *,
    problem_slug: str,
    outcome: str,
    pattern_tags: list[str] | None = None,
    time_taken_sec: int | None = None,
    attempted_at: datetime | None = None,
    notes: str | None = None,
    user_id: uuid.UUID | None = None,
) -> PracticeAttempt:
    """Record one attempt. Raises ``ValueError`` on an unknown outcome.

    ``pattern_tags`` defaults from the catalogue, so logging a catalogued
    problem does not require the operator to also remember what it teaches.
    """
    if outcome not in set(Outcome):
        raise ValueError(
            f"unknown outcome {outcome!r}; expected one of {sorted(o.value for o in Outcome)}"
        )
    from .catalog import PROBLEMS_BY_SLUG

    tags = pattern_tags
    if not tags:
        known = PROBLEMS_BY_SLUG.get(problem_slug)
        tags = list(known.patterns) if known else []

    attempt = PracticeAttempt(
        user_id=user_id or _operator_id(),
        problem_slug=problem_slug,
        pattern_tags=tags,
        outcome=outcome,
        time_taken_sec=time_taken_sec,
        attempted_at=attempted_at or datetime.now(UTC),
        notes=(notes or "").strip() or None,
    )
    session.add(attempt)
    session.flush()
    return attempt


def records(session: Session, *, user_id: uuid.UUID | None = None) -> list[PatternRecord]:
    """Every pattern with the operator's history, weakest and least-touched first."""
    uid = user_id or _operator_id()
    attempts = list(
        session.scalars(
            select(PracticeAttempt)
            .where(PracticeAttempt.user_id == uid)
            .order_by(PracticeAttempt.attempted_at.desc())
        )
    )

    by_pattern: dict[str, list[PracticeAttempt]] = {p.slug: [] for p in PATTERNS}
    for attempt in attempts:
        for tag in attempt.pattern_tags or []:
            if tag in by_pattern:
                by_pattern[tag].append(attempt)

    built = [PatternRecord(pattern=p, attempts=by_pattern[p.slug]) for p in PATTERNS]
    # Weak first (measured and struggling), then untouched, then the rest. An
    # unmeasured pattern outranks a solid one because the unknown is the risk.
    built.sort(key=lambda r: (not r.is_weak, not r.is_untouched, -(r.total - r.clean)))
    return built


def solved_slugs(session: Session, *, user_id: uuid.UUID | None = None) -> set[str]:
    """Problems already solved clean, so they stop being suggested as new work."""
    uid = user_id or _operator_id()
    rows = session.scalars(
        select(PracticeAttempt.problem_slug).where(
            PracticeAttempt.user_id == uid,
            PracticeAttempt.outcome == Outcome.SOLVED_CLEAN.value,
        )
    )
    return set(rows)


@dataclass(slots=True)
class Suggestion:
    """One problem worth doing next, and why."""

    problem: Problem
    pattern: Pattern
    reason: str
    is_review: bool = False


def next_problems(
    session: Session,
    *,
    limit: int = 8,
    pattern_slugs: list[str] | None = None,
    today: date | None = None,
    user_id: uuid.UUID | None = None,
) -> list[Suggestion]:
    """What to attempt next, at the operator's actual level.

    Level comes from their own record rather than from a self-assessment: a
    pattern with nothing logged starts at its easiest catalogued problem, and
    one already going well moves up. Nothing here is a difficulty *rating* of
    the operator -- it is a position in a list they can see.
    """
    done = solved_slugs(session, user_id=user_id)
    wanted = set(pattern_slugs or [])
    order = {"easy": 0, "medium": 1, "hard": 2}

    suggestions: list[Suggestion] = []
    for record in records(session, user_id=user_id):
        if wanted and record.slug not in wanted:
            continue

        candidates = [p for p in problems_for(record.slug) if p.slug not in done]
        if not candidates:
            continue

        # Where to enter the list. With no record, start at the easiest core
        # problem; with a solid record, skip what would be a warm-up.
        if record.is_untouched:
            pick = next((p for p in candidates if p.is_core), candidates[0])
            reason = f"No attempts logged for {record.pattern.name.lower()} yet — start here."
        elif record.is_weak:
            pick = next(
                (p for p in candidates if order.get(p.difficulty, 3) <= 1), candidates[0]
            )
            reason = f"{record.statement(today)} Worth more reps before moving up."
        else:
            harder = [p for p in candidates if order.get(p.difficulty, 3) >= 1]
            pick = harder[0] if harder else candidates[0]
            reason = f"{record.statement(today)} Ready for a harder one."

        suggestions.append(Suggestion(problem=pick, pattern=record.pattern, reason=reason))
        if len(suggestions) >= limit:
            break

    return suggestions


def prerequisite_gaps(session: Session, *, user_id: uuid.UUID | None = None) -> list[str]:
    """Patterns being attempted whose prerequisites have nothing logged.

    Struggling with dynamic programming when backtracking has never been touched
    is a different problem from struggling with dynamic programming, and it has
    a different fix.
    """
    by_slug = {r.slug: r for r in records(session, user_id=user_id)}
    gaps: list[str] = []
    for record in by_slug.values():
        if record.is_untouched:
            continue
        for prereq in PATTERNS_BY_SLUG[record.slug].prerequisites:
            prior = by_slug.get(prereq)
            if prior and prior.is_untouched:
                gaps.append(
                    f"You are attempting {record.pattern.name.lower()} with nothing logged "
                    f"for {prior.pattern.name.lower()}, which it builds on."
                )
    return gaps
