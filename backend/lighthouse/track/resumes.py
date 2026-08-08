"""Résumé versions, and which one went where.

Lighthouse does not generate résumés -- the operator writes their own. This
records which version was sent to which application, so the funnel can answer
the one question a funnel over a single undifferentiated pile cannot: whether
the rewrite actually did anything.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import Application, ResumeVersion
from .applications import OPERATOR_EVENTS


def _operator_id() -> uuid.UUID:
    from ..core.config import get_settings

    return get_settings().operator_id


def save_version(
    session: Session,
    *,
    label: str,
    extracted_text: str = "",
    notes: str | None = None,
    user_id: uuid.UUID | None = None,
) -> ResumeVersion:
    """Record a résumé the operator wrote. The text is what was extracted from
    the PDF, kept so a later tailor run can score against the version actually
    sent rather than whatever is on disk today."""
    if not label.strip():
        raise ValueError("a résumé version needs a label")
    version = ResumeVersion(
        user_id=user_id or _operator_id(),
        label=label.strip(),
        extracted_text=extracted_text,
        notes=(notes or "").strip() or None,
    )
    session.add(version)
    session.flush()
    return version


def list_versions(session: Session, *, user_id: uuid.UUID | None = None) -> list[ResumeVersion]:
    return list(
        session.scalars(
            select(ResumeVersion)
            .where(ResumeVersion.user_id == (user_id or _operator_id()))
            .order_by(ResumeVersion.created_at.desc())
        )
    )


def delete_version(session: Session, version_id: uuid.UUID) -> bool:
    version = session.get(ResumeVersion, version_id)
    if version is None:
        return False
    # Applications keep their row; the reference nulls out via ON DELETE SET
    # NULL. Losing which résumé was sent is worse than keeping a stale label,
    # so deleting a version is a deliberate act rather than a cleanup.
    session.delete(version)
    return True


@dataclass(slots=True)
class VersionOutcome:
    """One résumé version and what happened to the applications that used it."""

    version_id: uuid.UUID
    label: str
    applied: int
    responded: int

    @property
    def statement(self) -> str:
        """Counts only. A response rate over four applications is noise wearing
        a percent sign, and the whole point of tracking versions is to compare
        them honestly rather than to declare a winner early."""
        if self.applied == 0:
            return "not sent yet"
        return f"{self.responded} of {self.applied} got a response"


def outcomes_by_version(
    session: Session,
    states: list,
    *,
    user_id: uuid.UUID | None = None,
) -> list[VersionOutcome]:
    """Per-version response counts, over already-folded application states.

    "Responded" means the employer did something after the application went in
    -- an assessment, an interview, or a rejection. A rejection is a response:
    dropping it would flatter whichever résumé got the most silence.
    """
    versions = {v.id: v for v in list_versions(session, user_id=user_id)}
    if not versions:
        return []

    applied: dict[uuid.UUID, int] = {vid: 0 for vid in versions}
    responded: dict[uuid.UUID, int] = {vid: 0 for vid in versions}
    for state in states:
        vid = state.resume_version_id
        if vid not in versions:
            continue
        if state.applied_at is None:
            continue
        applied[vid] += 1
        if any(e.event_type not in OPERATOR_EVENTS for e in state.timeline):
            responded[vid] += 1

    return [
        VersionOutcome(
            version_id=vid,
            label=version.label,
            applied=applied[vid],
            responded=responded[vid],
        )
        for vid, version in versions.items()
    ]


def set_application_version(
    session: Session, application: Application, version_id: uuid.UUID | None
) -> None:
    """Attach a résumé version to an application, or clear it."""
    if version_id is not None and session.get(ResumeVersion, version_id) is None:
        raise ValueError("no such résumé version")
    application.resume_version_id = version_id
