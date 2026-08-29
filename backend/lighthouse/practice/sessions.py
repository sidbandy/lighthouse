"""The practice record, and the trend read back off it.

Layer 1 exists so the operator can watch themselves improve, and a measurement
taken once is not a measurement of anything. This is the table that turns four
numbers computed live into a line you can read.

**What is stored, and what deliberately is not.** Practice tells the operator
that nothing they say is recorded or kept. So a row here holds the numbers, the
date, the competency and the question -- and no transcript, no audio, and no
drift claims, because a drift claim quotes them out loud. The promise is worth
more than the convenience of being able to re-read an old answer.

Two rules keep a trend honest, and both are about refusing to compare things
that are not comparable:

* **Typed answers never enter a trend.** There is no duration for typed text, so
  its pace and length are not the same measurement as a spoken answer's. A
  session that was typed is recorded and excluded.
* **A missing metric is skipped, not zeroed.** ``silences`` only exists when the
  transcriber produced word timings. Counting its absence as "no long pauses"
  would invent an improvement out of a missing input.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.models import PracticeSession
from . import delivery, prosody
from .delivery import DeliveryReport, Trend
from .feedback import DriftFinding, StructureFinding

BEHAVIOURAL = "behavioural"
TECHNICAL = "technical"

SPOKEN = "spoken"
TYPED = "typed"

# How many sessions the history view reads back. Long enough to see a trend,
# short enough that the page stays one query.
HISTORY_LIMIT = 50


def _operator_id() -> uuid.UUID:
    return get_settings().operator_id


def record(
    session: Session,
    *,
    report: DeliveryReport,
    structure: list[StructureFinding] | None = None,
    drift: list[DriftFinding] | None = None,
    competency: str | None = None,
    question: str | None = None,
    answer_mode: str = SPOKEN,
    kind: str = BEHAVIOURAL,
    occurred_at: datetime | None = None,
    user_id: uuid.UUID | None = None,
) -> PracticeSession:
    """Store one answer's measurements. Raises ``ValueError`` on a bad mode or kind.

    Sessions too short to measure are still recorded. The attempt happened, and
    a history that silently drops the runs that went badly is a history that
    flatters.
    """
    if answer_mode not in (SPOKEN, TYPED):
        raise ValueError(f"unknown answer_mode {answer_mode!r}; expected 'spoken' or 'typed'")
    if kind not in (BEHAVIOURAL, TECHNICAL):
        raise ValueError(f"unknown kind {kind!r}; expected 'behavioural' or 'technical'")

    row = PracticeSession(
        user_id=user_id or _operator_id(),
        kind=kind,
        competency=competency,
        question=(question or "").strip() or None,
        answer_mode=answer_mode,
        duration_sec=report.duration_sec if answer_mode == SPOKEN else None,
        word_count=report.word_count,
        is_measurable=report.is_measurable,
        metrics={m.key: m.rounded for m in report.metrics},
        structure_present=[s.part for s in (structure or []) if s.present],
        drift_count=len(drift or []),
        occurred_at=occurred_at or datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def history(
    session: Session,
    *,
    kind: str = BEHAVIOURAL,
    competency: str | None = None,
    limit: int = HISTORY_LIMIT,
    user_id: uuid.UUID | None = None,
) -> list[PracticeSession]:
    """Sessions oldest first, which is the order a trend reads."""
    uid = user_id or _operator_id()
    stmt = (
        select(PracticeSession)
        .where(PracticeSession.user_id == uid, PracticeSession.kind == kind)
        .order_by(PracticeSession.occurred_at.desc())
        .limit(limit)
    )
    if competency:
        stmt = stmt.where(PracticeSession.competency == competency)
    return list(reversed(list(session.scalars(stmt))))


def trends(
    session: Session,
    *,
    kind: str = BEHAVIOURAL,
    user_id: uuid.UUID | None = None,
) -> list[Trend]:
    """Each delivery metric across the operator's own spoken sessions.

    Only spoken, measurable sessions count. ``delivery.trend`` returns ``None``
    below two points and says "not a trend yet" below three, so a new operator
    gets an empty list rather than a shape drawn through one dot.
    """
    rows = [
        r
        for r in history(session, kind=kind, user_id=user_id)
        if r.answer_mode == SPOKEN and r.is_measurable
    ]

    # Both vocabularies, because the acoustic filled-pause rate is the metric
    # most worth watching move and it would otherwise be stored and never read.
    # A session recorded before the audio pass existed simply has no value under
    # those keys, and a missing metric is skipped rather than zeroed.
    out: list[Trend] = []
    for key, label in {**delivery.METRIC_LABELS, **prosody.ACOUSTIC_LABELS}.items():
        values = [
            float(r.metrics[key]) for r in rows if r.metrics and r.metrics.get(key) is not None
        ]
        tracked = delivery.trend(key, label, values)
        if tracked is not None:
            out.append(tracked)
    return out


@dataclass(slots=True)
class StructureHabit:
    """How often one STAR part actually showed up.

    The most useful thing a practice record can tell someone is which part they
    keep leaving out -- a missing Result is the most common and costliest
    behavioural failure, and it is invisible in any single session.
    """

    part: str
    present: int
    total: int

    @property
    def missing(self) -> int:
        return self.total - self.present

    def statement(self) -> str:
        if self.total < 3:
            return f"{self.present} of {self.total} answers — too few to read yet."
        return f"Present in {self.present} of your last {self.total} answers."


def structure_habits(
    session: Session,
    *,
    parts: list[str],
    kind: str = BEHAVIOURAL,
    user_id: uuid.UUID | None = None,
) -> list[StructureHabit]:
    """Per-part presence across measurable sessions, most-missed first.

    ``parts`` is passed in rather than imported so this stays agnostic about
    which framework is being scored; STAR is the only one today.
    """
    rows = [r for r in history(session, kind=kind, user_id=user_id) if r.is_measurable]
    if not rows:
        return []
    habits = [
        StructureHabit(
            part=part,
            present=sum(1 for r in rows if part in (r.structure_present or [])),
            total=len(rows),
        )
        for part in parts
    ]
    habits.sort(key=lambda h: (-h.missing, h.part))
    return habits
