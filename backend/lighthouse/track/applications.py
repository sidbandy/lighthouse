"""Application state, derived by folding the event log.

``Application`` has no status column: the stage is computed from its events on
every read. That keeps the dates every wait-time figure depends on, makes a
correction additive, and lets silence be measured rather than guessed at.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import events as event_log
from ..core.models import Application, Posting

ENTITY = "application"


class Stage(IntEnum):
    """How far an application has got. Ordered so progress is a comparison.

    Terminal outcomes sit above the live stages so that a rejection at any point
    still folds to "rejected" rather than being outranked by an earlier
    interview.
    """

    SAVED = 0
    APPLIED = 1
    ASSESSMENT = 2
    INTERVIEW = 3
    FINAL = 4
    OFFER = 5
    # Terminal.
    REJECTED = 90
    WITHDRAWN = 91
    ACCEPTED = 92

    @property
    def is_terminal(self) -> bool:
        return self >= Stage.REJECTED

    @property
    def is_live(self) -> bool:
        """Still in play, and therefore still worth chasing."""
        return not self.is_terminal and self >= Stage.APPLIED


# The event vocabulary, and the stage each implies. Kept as data rather than a
# chain of ifs so the board, the API and the tests all read the same table.
EVENT_STAGES: dict[str, Stage] = {
    "saved": Stage.SAVED,
    "applied": Stage.APPLIED,
    "assessment_received": Stage.ASSESSMENT,
    "assessment_completed": Stage.ASSESSMENT,
    "interview_scheduled": Stage.INTERVIEW,
    "interview_completed": Stage.INTERVIEW,
    "final_round": Stage.FINAL,
    "offer": Stage.OFFER,
    "rejected": Stage.REJECTED,
    "withdrawn": Stage.WITHDRAWN,
    "accepted": Stage.ACCEPTED,
}

STAGE_LABELS: dict[Stage, str] = {
    Stage.SAVED: "Saved",
    Stage.APPLIED: "Applied",
    Stage.ASSESSMENT: "Assessment",
    Stage.INTERVIEW: "Interview",
    Stage.FINAL: "Final round",
    Stage.OFFER: "Offer",
    Stage.REJECTED: "Rejected",
    Stage.WITHDRAWN: "Withdrawn",
    Stage.ACCEPTED: "Accepted",
}

# Events that are the *operator* acting rather than the employer responding.
# Silence is measured from the last employer signal, so these do not reset it —
# otherwise adding a note to a dead application would make it look alive.
OPERATOR_EVENTS = frozenset({"saved", "applied", "note", "withdrawn"})


@dataclass(slots=True)
class StageEntry:
    """One dated step in an application's history."""

    event_type: str
    stage: Stage
    occurred_at: datetime
    note: str = ""

    @property
    def label(self) -> str:
        return STAGE_LABELS[self.stage]


@dataclass(slots=True)
class ApplicationState:
    """An application, folded. Every field here is observed, never predicted."""

    application_id: uuid.UUID
    posting_id: uuid.UUID
    stage: Stage
    timeline: list[StageEntry] = field(default_factory=list)
    notes: str | None = None
    resume_version_id: uuid.UUID | None = None

    @property
    def applied_at(self) -> datetime | None:
        return next((e.occurred_at for e in self.timeline if e.event_type == "applied"), None)

    @property
    def last_employer_signal(self) -> datetime | None:
        """When the employer last did anything. The clock silence runs from."""
        signals = [e.occurred_at for e in self.timeline if e.event_type not in OPERATOR_EVENTS]
        return max(signals) if signals else None

    def days_silent(self, today: date | None = None) -> int | None:
        """Days since the last employer signal, or since applying if there has
        never been one. ``None`` when the application is not waiting on anyone.

        This is the entire ghosting feature. It is a subtraction between two
        real dates, and it is reported as such.
        """
        if not self.stage.is_live:
            return None
        since = self.last_employer_signal or self.applied_at
        if since is None:
            return None
        reference = today or datetime.now(UTC).date()
        return max(0, (reference - since.date()).days)

    def silence_note(self, today: date | None = None) -> str | None:
        """The dated statement of silence, or ``None`` if there is nothing to
        say. Deliberately a sentence of fact with no verdict attached.

        Nothing is said on the day itself: "0 days since you applied, no
        response" is true and useless, and printing it on every row the operator
        has just logged trains them to ignore the line that matters at day 40.
        """
        days = self.days_silent(today)
        if days is None or days == 0:
            return None
        anchor = "since the last update" if self.last_employer_signal else "since you applied"
        return f"{days} day{'s' if days != 1 else ''} {anchor}, no response"


def fold(
    application: Application, entries: list, *, include_notes: bool = True
) -> ApplicationState:
    """Fold an application's events into its current state.

    The stage is the highest one reached: an interview does not stop being a
    fact because a rejection followed, and terminal stages sort above the live
    ones so the rejection still wins. Nothing is inferred that was not logged.
    """
    timeline: list[StageEntry] = []
    for event in entries:
        stage = EVENT_STAGES.get(event.event_type)
        if stage is None:
            # Notes and unrecognised types are not stages, so they stay out of
            # the fold. The raw log still has them.
            continue
        timeline.append(
            StageEntry(
                event_type=event.event_type,
                stage=stage,
                occurred_at=event.occurred_at,
                note=str(event.payload.get("note", "")) if include_notes else "",
            )
        )

    stage = max((e.stage for e in timeline), default=Stage.SAVED)
    return ApplicationState(
        application_id=application.id,
        posting_id=application.posting_id,
        stage=stage,
        timeline=timeline,
        notes=application.notes,
        resume_version_id=application.resume_version_id,
    )


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def get_or_create(
    session: Session,
    posting_id: uuid.UUID,
    *,
    mark_saved: bool = True,
    user_id: uuid.UUID | None = None,
) -> tuple[Application, bool]:
    """The application for a posting, creating it (as ``saved``) if new.

    Returns ``(application, created)``. One application per posting per
    operator, enforced by a unique constraint — applying twice to the same role
    is a mistake, not a state.

    ``mark_saved=False`` skips the opening ``saved`` event, for callers logging a
    real stage in the same breath -- otherwise a back-dated application gets a
    "saved" stamped with the current time, out of order with its own timeline.
    """
    from ..core.config import get_settings

    uid = user_id or get_settings().operator_id
    existing = session.scalar(
        select(Application).where(Application.user_id == uid, Application.posting_id == posting_id)
    )
    if existing is not None:
        return existing, False

    application = Application(user_id=uid, posting_id=posting_id)
    session.add(application)
    session.flush()
    if mark_saved:
        event_log.record(
            session,
            entity_type=ENTITY,
            entity_id=application.id,
            event_type="saved",
            user_id=uid,
        )
    return application, True


def log_event(
    session: Session,
    application: Application,
    event_type: str,
    *,
    occurred_at: datetime | None = None,
    note: str = "",
    user_id: uuid.UUID | None = None,
):
    """Record a stage change. Raises ``ValueError`` on an unknown event type."""
    if event_type not in EVENT_STAGES and event_type != "note":
        raise ValueError(
            f"unknown event type {event_type!r}; expected one of {sorted(EVENT_STAGES) + ['note']}"
        )
    return event_log.record(
        session,
        entity_type=ENTITY,
        entity_id=application.id,
        event_type=event_type,
        payload={"note": note} if note else {},
        occurred_at=occurred_at,
        user_id=user_id,
    )


def board(
    session: Session, *, user_id: uuid.UUID | None = None
) -> list[tuple[ApplicationState, Posting]]:
    """Every application with its posting, folded, newest activity first.

    One query for the applications, one for their postings and one for the
    whole event log — the board stays a constant number of round trips however
    many applications it holds.
    """
    from ..core.config import get_settings

    uid = user_id or get_settings().operator_id
    applications = list(session.scalars(select(Application).where(Application.user_id == uid)))
    if not applications:
        return []

    histories = event_log.history_for_many(
        session,
        entity_type=ENTITY,
        entity_ids=[a.id for a in applications],
        user_id=uid,
    )
    postings = {
        p.id: p
        for p in session.scalars(
            select(Posting).where(Posting.id.in_([a.posting_id for a in applications]))
        )
    }

    rows = [
        (fold(a, histories.get(a.id, [])), postings[a.posting_id])
        for a in applications
        if a.posting_id in postings
    ]
    epoch = datetime.min.replace(tzinfo=UTC)
    rows.sort(
        key=lambda row: max((e.occurred_at for e in row[0].timeline), default=epoch),
        reverse=True,
    )
    return rows
