"""The append-only event log.

Nothing is updated in place. ``occurred_at`` is when something happened,
``recorded_at`` is when it was logged; they routinely differ by days, so
process metrics use the former and freshness checks the latter.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Event


def _operator_id() -> uuid.UUID:
    return get_settings().operator_id


def record(
    session: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    event_type: str,
    payload: dict | None = None,
    occurred_at: datetime | None = None,
    user_id: uuid.UUID | None = None,
) -> Event:
    """Append one event.

    ``occurred_at`` defaults to now, which is right for something the operator
    is doing as they log it, and wrong for something they are back-filling — so
    every caller that knows the real date is expected to pass it.
    """
    event = Event(
        user_id=user_id or _operator_id(),
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload=payload or {},
        occurred_at=occurred_at or datetime.now(UTC),
    )
    session.add(event)
    session.flush()
    return event


def history(
    session: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> list[Event]:
    """Every event for one entity, oldest first.

    Ordered by ``occurred_at`` and then ``recorded_at``, so two events entered
    on the same day still fold in the order they were logged rather than in
    whatever order the database happens to return.
    """
    return list(
        session.scalars(
            select(Event)
            .where(
                Event.user_id == (user_id or _operator_id()),
                Event.entity_type == entity_type,
                Event.entity_id == entity_id,
            )
            .order_by(Event.occurred_at, Event.recorded_at)
        )
    )


def discard(
    session: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> int:
    """Delete one entity's whole history. The single exception to append-only.

    Only for an entity being removed because tracking it was a mistake: there is
    no fact left to preserve, and the alternative is a log that accumulates
    events for things that no longer exist and skews any later "how much have I
    logged" figure. Returns the number removed.
    """
    result = session.execute(
        delete(Event).where(
            Event.user_id == (user_id or _operator_id()),
            Event.entity_type == entity_type,
            Event.entity_id == entity_id,
        )
    )
    return int(result.rowcount or 0)


def history_for_many(
    session: Session,
    *,
    entity_type: str,
    entity_ids: list[uuid.UUID],
    user_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, list[Event]]:
    """The same, for a whole board in one query rather than one per row."""
    if not entity_ids:
        return {}
    rows = session.scalars(
        select(Event)
        .where(
            Event.user_id == (user_id or _operator_id()),
            Event.entity_type == entity_type,
            Event.entity_id.in_(entity_ids),
        )
        .order_by(Event.occurred_at, Event.recorded_at)
    )
    grouped: dict[uuid.UUID, list[Event]] = {eid: [] for eid in entity_ids}
    for event in rows:
        grouped.setdefault(event.entity_id, []).append(event)
    return grouped
