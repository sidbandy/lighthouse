"""Spaced repetition, designed around the week you miss.

SM-2 intervals, which are a solved problem and are implemented rather than
reinvented. Everything interesting here is the part that keeps someone using it
in week six, because that is where study tools actually die:

* **No growing overdue counter.** Ever. Coming back after ten days to "47 cards
  due" is the moment people close the tab and do not reopen it. Returning after
  a gap shows a normal day's work, prioritised by what has decayed most.
* **A hard daily cap**, regardless of what is technically due.
* **A gap is not a failure.** Missing a week does not reset intervals or
  penalise ease. The schedule slid; the knowledge did not evaporate.

Reviews are derived from the attempt log rather than stored in their own table.
An attempt already records the problem, the outcome and the date, which is
exactly what SM-2 needs -- and a second source of truth for "how did that go"
would be one that could disagree with the first.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import PracticeAttempt
from .attempts import Outcome
from .catalog import PROBLEMS_BY_SLUG, Problem

# SM-2's step ladder, in days. A clean solve advances one step; anything less
# drops back, and a failure returns to the start.
INTERVALS: tuple[int, ...] = (1, 3, 7, 16, 35, 90)

# However much is technically due. Twenty is already a long evening, and a cap
# that is occasionally generous is better than one that is occasionally
# impossible.
DAILY_CAP = 12

# Below this the review queue is not worth surfacing at all -- there is nothing
# to space out yet.
MIN_HISTORY = 1


def _step_for(outcomes: list[str]) -> int:
    """Where a problem sits on the ladder, from its attempt history.

    Replayed from the start each time rather than stored. It is a handful of
    integers over a handful of attempts, and deriving it means the ladder can be
    changed without a migration or a backfill.
    """
    step = 0
    for outcome in outcomes:
        if outcome == Outcome.SOLVED_CLEAN:
            step = min(step + 1, len(INTERVALS) - 1)
        elif outcome == Outcome.FAILED:
            step = 0
        else:
            # A hint or an overrun is real partial recall: hold position rather
            # than advancing. Dropping to zero would punish honesty, and the
            # operator is the only one logging these.
            step = max(step - 1, 0)
    return step


@dataclass(slots=True)
class Review:
    """One problem due for another look."""

    problem_slug: str
    title: str
    step: int
    last_attempted: datetime
    due_on: date
    last_outcome: str
    problem: Problem | None = None

    def days_overdue(self, today: date | None = None) -> int:
        return max(0, ((today or datetime.now(UTC).date()) - self.due_on).days)

    @property
    def url(self) -> str:
        if self.problem:
            return self.problem.url
        return f"https://leetcode.com/problems/{self.problem_slug}/"

    def statement(self, today: date | None = None) -> str:
        over = self.days_overdue(today)
        interval = INTERVALS[self.step]
        if over == 0:
            return f"Due today, on a {interval}-day interval."
        return f"Last seen {over + interval} days ago, on a {interval}-day interval."


@dataclass(slots=True)
class ReviewQueue:
    """Today's reviews, already capped."""

    due: list[Review] = field(default_factory=list)
    # How many were due before the cap. Shown as context, never as a backlog to
    # clear -- the whole point is that the number does not accumulate on screen.
    total_due: int = 0
    upcoming: list[Review] = field(default_factory=list)

    @property
    def was_capped(self) -> bool:
        return self.total_due > len(self.due)

    def note(self) -> str:
        if not self.due and not self.upcoming:
            return (
                "Nothing to review yet. Log a few attempts and this fills in on its own — "
                "problems come back at widening intervals, and a missed week costs nothing."
            )
        if not self.due:
            nxt = min(r.due_on for r in self.upcoming)
            return f"Nothing due today. Next review {nxt.isoformat()}."
        if self.was_capped:
            return (
                f"{len(self.due)} to review today. More had drifted past their date while you "
                "were away; they are queued behind these, not stacked on top of you."
            )
        return f"{len(self.due)} to review today."


def _operator_id() -> uuid.UUID:
    from ..core.config import get_settings

    return get_settings().operator_id


def build_queue(
    session: Session,
    *,
    today: date | None = None,
    cap: int = DAILY_CAP,
    user_id: uuid.UUID | None = None,
) -> ReviewQueue:
    """What to review now, most decayed first.

    "Most decayed" rather than "longest overdue" is deliberate: a one-day
    interval three days late has lost more than a ninety-day interval three days
    late, and after a gap the operator should meet the things closest to being
    forgotten, not the things with the oldest timestamp.
    """
    uid = user_id or _operator_id()
    today = today or datetime.now(UTC).date()

    attempts = list(
        session.scalars(
            select(PracticeAttempt)
            .where(PracticeAttempt.user_id == uid)
            .order_by(PracticeAttempt.attempted_at)
        )
    )
    if len(attempts) < MIN_HISTORY:
        return ReviewQueue()

    history: dict[str, list[PracticeAttempt]] = {}
    for attempt in attempts:
        history.setdefault(attempt.problem_slug, []).append(attempt)

    due: list[Review] = []
    upcoming: list[Review] = []
    for slug, rows in history.items():
        step = _step_for([r.outcome for r in rows])
        last = rows[-1]
        due_on = last.attempted_at.astimezone(UTC).date() + timedelta(days=INTERVALS[step])
        known = PROBLEMS_BY_SLUG.get(slug)
        review = Review(
            problem_slug=slug,
            title=known.title if known else slug.replace("-", " ").title(),
            step=step,
            last_attempted=last.attempted_at,
            due_on=due_on,
            last_outcome=last.outcome,
            problem=known,
        )
        (due if due_on <= today else upcoming).append(review)

    # Decay ratio: how far past its interval a card is, relative to that
    # interval. A short interval decays faster, so it surfaces first.
    def decay(review: Review) -> float:
        interval = INTERVALS[review.step] or 1
        return review.days_overdue(today) / interval

    due.sort(key=lambda r: (-decay(r), r.due_on))
    upcoming.sort(key=lambda r: r.due_on)

    return ReviewQueue(due=due[:cap], total_due=len(due), upcoming=upcoming[:10])
