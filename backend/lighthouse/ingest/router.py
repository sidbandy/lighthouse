"""Ingest endpoints.

Kept separate from Discover because these mutate: they go out to the network
and rewrite the posting table. Scheduled runs live in the worker; these are the
manual trigger and the catalogue view.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.db import get_session
from ..discover.schemas import IngestResultOut, IngestSourceResult
from . import runner
from .pipeline import run_ingest
from .registry import all_connectors
from .seasons import applyable_cycles

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


class RefreshStatusOut(BaseModel):
    """Whether a refresh is in flight, and how the last one went."""

    is_running: bool
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: str | None = None
    error: str | None = None
    created: int = 0
    updated: int = 0
    sources_ok: int = 0
    sources_failed: int = 0
    accepted: bool = Field(
        default=True,
        description="False when a refresh was asked for while one was already running.",
    )


class SourceInfo(BaseModel):
    source_id: str
    tier: int
    description: str


class CycleInfo(BaseModel):
    term_label: str
    season: str
    year: int
    start_date: date


@router.get("/sources", response_model=list[SourceInfo])
def list_sources() -> list[SourceInfo]:
    """Every registered feed, with the tier it belongs to."""
    return [
        SourceInfo(source_id=c.source_id, tier=c.tier, description=c.description)
        for c in sorted(all_connectors(), key=lambda c: (c.tier, c.source_id))
    ]


@router.get("/cycles", response_model=list[CycleInfo])
def list_cycles(today: date | None = None) -> list[CycleInfo]:
    """Cycles still open to apply to, soonest first.

    This is what makes the tool advance with the calendar rather than being
    pinned to one Summer cycle.
    """
    return [
        CycleInfo(term_label=c.label, season=c.season.value, year=c.year, start_date=c.start_date)
        for c in applyable_cycles(today or date.today())
    ]


@router.post("/run", response_model=IngestResultOut)
def trigger_ingest(
    session: Session = Depends(get_session),
    max_tier: int = Query(
        default=2,
        ge=1,
        le=5,
        description="Tiers 1-2 are the fast path and already give a complete list.",
    ),
    today: date | None = None,
) -> IngestResultOut:
    """Run an ingest now.

    Synchronous on purpose: a single operator triggering a refresh wants to see
    the result, and the fast path takes seconds.
    """
    report = run_ingest(session, max_tier=max_tier, today=today)
    session.commit()
    return IngestResultOut(
        summary=report.summary(),
        raw_count=report.raw_count,
        merged_count=report.merged_count,
        created=report.created,
        updated=report.updated,
        skipped_not_applyable=report.skipped_not_applyable,
        term_rules=report.term_rules,
        sources=[
            IngestSourceResult(
                source_id=s.source_id,
                ok=s.ok,
                row_count=s.row_count,
                error=s.error,
                quarantined=s.quarantined,
            )
            for s in report.sources
        ],
    )


def _status_out(state: runner.RunState, *, accepted: bool = True) -> RefreshStatusOut:
    return RefreshStatusOut(
        is_running=state.is_running,
        started_at=state.started_at,
        finished_at=state.finished_at,
        summary=state.summary,
        error=state.error,
        created=state.created,
        updated=state.updated,
        sources_ok=state.sources_ok,
        sources_failed=state.sources_failed,
        accepted=accepted,
    )


@router.post("/refresh", response_model=RefreshStatusOut, status_code=202)
def start_refresh(
    max_tier: int = Query(
        default=3,
        ge=1,
        le=5,
        description="Tier 3 adds the direct ATS boards, which are the only source of "
        "full descriptions -- and descriptions are what match scoring and the brief need.",
    ),
) -> RefreshStatusOut:
    """Kick off an ingest in the background and return immediately.

    Poll ``GET /api/ingest/refresh`` for progress. A request made while a run is
    already in flight is refused with ``accepted=false`` rather than queued:
    two concurrent runs would race on the same dedup keys for no benefit.
    """
    accepted, state = runner.start(max_tier=max_tier)
    return _status_out(state, accepted=accepted)


@router.get("/refresh", response_model=RefreshStatusOut)
def refresh_status() -> RefreshStatusOut:
    """Whether a refresh is running, and the outcome of the last one."""
    return _status_out(runner.status())
