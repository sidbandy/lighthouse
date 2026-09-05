"""Running an alert: pick, render, deliver, and say what happened.

The cutoff comes from the run record. ``ingest_runs`` already stores when each
run started, so "new since the last run" is the previous run's ``started_at``
and needs no extra state -- and because the row is written even when a run
dies, a killed run does not silently widen the next window into a flood.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import IngestRun
from . import message as message_render
from .delivery import DeliveryResult, build_message, transport_from_settings
from .selection import AlertCandidate, select_new_postings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AlertRun:
    """What the alert did, in enough detail to debug it from a log line."""

    since: datetime | None
    candidates: list[AlertCandidate]
    delivered: DeliveryResult
    subject: str = ""
    body: str = ""

    @property
    def count(self) -> int:
        return len(self.candidates)


def previous_run_start(session: Session, *, before: datetime | None = None) -> datetime | None:
    """When the run before this one began.

    None on the very first run, which is deliberately treated as "no window"
    rather than "everything": alerting on 23,000 rows the first time would be
    the last time anyone read one.
    """
    stmt = select(IngestRun.started_at).order_by(IngestRun.started_at.desc())
    if before is not None:
        stmt = stmt.where(IngestRun.started_at < before)
    return session.scalars(stmt.limit(1)).first()


def run_alert(
    session: Session,
    *,
    since: datetime | None = None,
    transport=None,
    settings=None,
    today: date | None = None,
) -> AlertRun:
    """Select, render and deliver. Never raises on a delivery problem."""
    from ..core.config import get_settings

    settings = settings or get_settings()
    today = today or datetime.now(UTC).date()

    if since is None:
        return AlertRun(
            since=None,
            candidates=[],
            delivered=DeliveryResult(
                False,
                "No previous run to compare against, so there is no 'new' yet. "
                "The next run will have one.",
            ),
        )

    candidates = select_new_postings(
        session,
        since=since,
        min_match=settings.alert_min_match,
        skip_ghost=tuple(settings.alert_skip_ghost),
        limit=settings.alert_max_items,
        today=today,
    )

    subject = message_render.subject(candidates, today=today)
    body = message_render.render(candidates, today=today)

    if not candidates:
        # Silence is the right outcome, and saying so is not the same as
        # sending "nothing happened" to someone's inbox twice a day.
        return AlertRun(
            since=since,
            candidates=[],
            delivered=DeliveryResult(False, "Nothing cleared the bar; no message sent."),
            subject=subject,
            body=body,
        )

    transport = transport or transport_from_settings(settings)
    if transport is None:
        return AlertRun(
            since=since,
            candidates=candidates,
            delivered=DeliveryResult(
                False,
                "Alerts are not configured. Set LIGHTHOUSE_ALERT_EMAIL_TO and "
                "LIGHTHOUSE_SMTP_HOST to receive these.",
            ),
            subject=subject,
            body=body,
        )

    result = transport.send(
        build_message(
            to=settings.alert_email_to,
            sender=settings.alert_email_from,
            subject=subject,
            body=body,
        )
    )
    logger.info("alerts: %d candidates, delivery=%s", len(candidates), result.reason)
    return AlertRun(
        since=since, candidates=candidates, delivered=result, subject=subject, body=body
    )
