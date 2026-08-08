"""Discover endpoints: the ranked, filtered, deduplicated posting list."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.db import get_session
from ..core.models import EmploymentType, RoleFamily, Season, Sponsorship
from ..track import applications as track_applications
from ..track.schemas import TrackedStateOut
from . import ranking, service
from .schemas import (
    CycleCount,
    LaneBucketOut,
    PostingDetail,
    PostingPage,
    PostingSummary,
    SourceHealthOut,
)

router = APIRouter(prefix="/api", tags=["discover"])


def _attach_tracked(session: Session, items: list[PostingSummary]) -> None:
    """Mark whichever of ``items`` are already on the board.

    Done here rather than in the service so Discover's query layer stays unaware
    of Track. Two extra queries for the whole page, however long it is.
    """
    if not items:
        return
    states = track_applications.states_for_postings(session, [item.id for item in items])
    if not states:
        return
    for item in items:
        state = states.get(item.id)
        if state is not None:
            item.tracked = TrackedStateOut.from_state(state)


@router.get("/postings", response_model=PostingPage)
def list_postings(
    session: Session = Depends(get_session),
    season: list[Season] = Query(default=[]),
    term_year: list[int] = Query(default=[]),
    employment_type: list[EmploymentType] = Query(default=[]),
    role_family: list[RoleFamily] = Query(default=[]),
    sponsorship: list[Sponsorship] = Query(default=[]),
    state: list[str] = Query(default=[], description="Two-letter state codes, e.g. TX"),
    search: str | None = None,
    active_only: bool = True,
    remote_only: bool = False,
    with_description_only: bool = Query(
        default=False,
        description="Only postings carrying a full description, which is stronger match evidence.",
    ),
    include_unknown_term: bool = Query(
        default=True,
        description="Include postings whose cycle could not be resolved. On by default: "
        "they are real roles and hiding them would trade a visible gap for an invisible one.",
    ),
    applyable_only: bool = Query(
        default=True, description="Only cycles that have not already started."
    ),
    posted_within_days: int | None = Query(default=None, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    today: date | None = Query(default=None, description="Override 'today' for testing."),
) -> PostingPage:
    filters = service.PostingFilters(
        seasons=season,
        term_years=term_year,
        employment_types=[e.value for e in employment_type],
        role_families=[r.value for r in role_family],
        sponsorship=[s.value for s in sponsorship],
        states=state,
        search=search,
        active_only=active_only,
        remote_only=remote_only,
        with_description_only=with_description_only,
        include_unknown_term=include_unknown_term,
        applyable_only=applyable_only,
        posted_within_days=posted_within_days,
        limit=limit,
        offset=offset,
    )
    items, total = service.list_postings(session, filters, today)
    _attach_tracked(session, items)
    return PostingPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/discover", response_model=list[LaneBucketOut])
def discover(
    session: Session = Depends(get_session),
    season: list[Season] = Query(default=[]),
    employment_type: list[EmploymentType] = Query(default=[]),
    role_family: list[RoleFamily] = Query(default=[]),
    sponsorship: list[Sponsorship] = Query(default=[]),
    state: list[str] = Query(default=[], description="Two-letter state codes, e.g. TX"),
    search: str | None = None,
    remote_only: bool = False,
    posted_within_days: int | None = Query(default=None, ge=1, le=365),
    with_description_only: bool = Query(
        default=False,
        description="Only postings carrying a description, so match scores rest on real evidence.",
    ),
    per_lane: int = Query(default=15, ge=1, le=50),
    today: date | None = None,
) -> list[LaneBucketOut]:
    """The three-lane view: reach / target / safety, scored against the corpus.

    This is the headline Discover surface. With an empty corpus every score is
    0 and the lanes fall back to selectivity alone.
    """
    filters = service.PostingFilters(
        seasons=season,
        employment_types=[e.value for e in employment_type],
        role_families=[r.value for r in role_family],
        sponsorship=[s.value for s in sponsorship],
        states=state,
        search=search,
        remote_only=remote_only,
        posted_within_days=posted_within_days,
        with_description_only=with_description_only,
    )
    buckets = ranking.three_lane_view(session, filters, per_lane=per_lane, today=today)
    out = ranking.lane_view_to_out(buckets)
    _attach_tracked(session, [p for bucket in out for p in bucket.postings])
    return out


@router.get("/postings/{posting_id}", response_model=PostingDetail)
def get_posting(posting_id: UUID, session: Session = Depends(get_session)) -> PostingDetail:
    posting = service.get_posting(session, posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail="Posting not found")
    _attach_tracked(session, [posting])
    return posting


@router.get("/cycles", response_model=list[CycleCount])
def cycle_counts(
    session: Session = Depends(get_session), today: date | None = None
) -> list[CycleCount]:
    """Live posting counts per still-applyable cycle."""
    return service.cycle_counts(session, today)


@router.get("/sources/health", response_model=list[SourceHealthOut])
def source_health(session: Session = Depends(get_session)) -> list[SourceHealthOut]:
    """Per-source liveness, so a feed that quietly died is visible."""
    return [SourceHealthOut.model_validate(h) for h in service.source_health(session)]


@router.get("/sources/breakdown", response_model=dict[str, int])
def source_breakdown(session: Session = Depends(get_session)) -> dict[str, int]:
    """How many live postings each source currently contributes."""
    return service.source_breakdown(session)
