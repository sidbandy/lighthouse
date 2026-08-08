"""Ingest endpoints.

Kept separate from Discover because these mutate: they go out to the network
and rewrite the posting table.

A run is always started in the background and polled. There was a synchronous
trigger here too, which is the wrong shape twice over: a full run takes about a
minute, which no HTTP request should hold open, and a host that freezes
processes between requests would kill it halfway. The CLI covers the case where
someone wants to watch a run finish.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from . import runner
from .registry import all_connectors

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


@router.get("/sources", response_model=list[SourceInfo])
def list_sources() -> list[SourceInfo]:
    """Every registered feed, with the tier it belongs to."""
    return [
        SourceInfo(source_id=c.source_id, tier=c.tier, description=c.description)
        for c in sorted(all_connectors(), key=lambda c: (c.tier, c.source_id))
    ]


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
