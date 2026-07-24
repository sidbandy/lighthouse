"""Querying the posting list.

The filters here are the ones that decide whether a list of 26,000 postings is
usable or noise. Sponsorship and cycle are first-class rather than afterthoughts:
showing an operator roles they are not eligible for, or roles for a cycle that
already started, wastes the scarcest resource in a job search, which is
attention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.models import Company, Posting, PostingSource, Season, SourceHealth
from ..ingest.seasons import Cycle, applyable_cycles
from .ghost import assess
from .schemas import (
    CycleCount,
    GhostAssessmentOut,
    GhostSignalOut,
    PostingDetail,
    PostingSummary,
    SourceSighting,
)


@dataclass(slots=True)
class PostingFilters:
    """Everything the Discover view can filter on."""

    seasons: list[Season] = field(default_factory=list)
    term_years: list[int] = field(default_factory=list)
    employment_types: list[str] = field(default_factory=list)
    role_families: list[str] = field(default_factory=list)
    sponsorship: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    search: str | None = None

    active_only: bool = True
    remote_only: bool = False
    with_description_only: bool = False
    # Unresolved-term rows are shown by default. They are real postings; hiding
    # them would trade a visible gap for an invisible one.
    include_unknown_term: bool = True
    applyable_only: bool = True
    posted_within_days: int | None = None

    limit: int = 50
    offset: int = 0


def _term_label(posting: Posting) -> str | None:
    if posting.season is None or posting.term_year is None:
        return None
    return f"{posting.season.value.capitalize()} {posting.term_year}"


def _age_days(posting: Posting, today: date) -> int | None:
    if posting.posted_at is None:
        return None
    return max(0, (today - posting.posted_at.astimezone(UTC).date()).days)


def _cycle_predicate(cycles: list[Cycle]):
    """SQL matching any of the given (season, year) pairs."""
    return or_(*[(Posting.season == c.season) & (Posting.term_year == c.year) for c in cycles])


def _apply_filters(stmt: Select, filters: PostingFilters, today: date) -> Select:
    if filters.active_only:
        stmt = stmt.where(Posting.is_active.is_(True))
    if filters.remote_only:
        stmt = stmt.where(Posting.is_remote.is_(True))
    if filters.with_description_only:
        stmt = stmt.where(Posting.description_available.is_(True))

    if filters.seasons:
        stmt = stmt.where(Posting.season.in_(filters.seasons))
    if filters.term_years:
        stmt = stmt.where(Posting.term_year.in_(filters.term_years))
    elif filters.applyable_only:
        # Restrict to cycles that have not started. Unresolved-term rows are
        # kept when requested, since we cannot prove they are stale.
        cycles = applyable_cycles(today)
        predicate = _cycle_predicate(cycles)
        if filters.include_unknown_term:
            predicate = or_(predicate, Posting.season.is_(None))
        stmt = stmt.where(predicate)

    if not filters.include_unknown_term:
        stmt = stmt.where(Posting.season.isnot(None))

    if filters.employment_types:
        stmt = stmt.where(Posting.employment_type.in_(filters.employment_types))
    if filters.role_families:
        stmt = stmt.where(Posting.role_family.in_(filters.role_families))
    if filters.sponsorship:
        stmt = stmt.where(Posting.sponsorship.in_(filters.sponsorship))

    if filters.states:
        upper = [s.upper() for s in filters.states]
        stmt = stmt.where(
            or_(
                *[Posting.location_labels.any(f"%, {state}") for state in upper],
                *[Posting.locations.contains([{"state": state}]) for state in upper],
            )
        )

    if filters.posted_within_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=filters.posted_within_days)
        stmt = stmt.where(Posting.posted_at >= cutoff)

    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        stmt = stmt.where(or_(Posting.title.ilike(pattern), Company.name.ilike(pattern)))

    return stmt


def list_postings(
    session: Session, filters: PostingFilters, today: date | None = None
) -> tuple[list[PostingSummary], int]:
    """Return a page of postings and the total matching the filters."""
    today = today or datetime.now(UTC).date()

    base = select(Posting).join(Company, Company.id == Posting.company_id)
    filtered = _apply_filters(base, filters, today)

    total = session.scalar(
        _apply_filters(
            select(func.count(Posting.id)).join(Company, Company.id == Posting.company_id),
            filters,
            today,
        )
    )

    rows = session.scalars(
        filtered.options(selectinload(Posting.company), selectinload(Posting.sources))
        # Newest first, with undated rows last rather than sorted arbitrarily.
        .order_by(Posting.posted_at.desc().nullslast(), Posting.first_seen_at.desc())
        .limit(filters.limit)
        .offset(filters.offset)
    ).all()

    return [_to_summary(p, today) for p in rows], int(total or 0)


def _to_summary(posting: Posting, today: date) -> PostingSummary:
    source_ids = sorted({s.source_id for s in posting.sources})
    return PostingSummary(
        id=posting.id,
        company_name=posting.company.name,
        title=posting.title,
        url=posting.url,
        season=posting.season,
        term_year=posting.term_year,
        term_label=_term_label(posting),
        term_rule=posting.term_rule,
        term_evidence=posting.term_evidence,
        employment_type=posting.employment_type,
        role_family=posting.role_family,
        sponsorship=posting.sponsorship,
        location_labels=posting.location_labels or [],
        is_remote=posting.is_remote,
        is_active=posting.is_active,
        description_available=posting.description_available,
        posted_at=posting.posted_at,
        age_days=_age_days(posting, today),
        source_ids=source_ids,
        source_count=len(source_ids),
    )


def get_posting(session: Session, posting_id, today: date | None = None) -> PostingDetail | None:
    today = today or datetime.now(UTC).date()
    posting = session.scalar(
        select(Posting)
        .where(Posting.id == posting_id)
        .options(selectinload(Posting.company), selectinload(Posting.sources))
    )
    if posting is None:
        return None

    summary = _to_summary(posting, today)
    assessment = assess(posting, source_count=summary.source_count, today=today)
    return PostingDetail(
        **summary.model_dump(),
        ghost=GhostAssessmentOut(
            label=assessment.label.value,
            summary=assessment.summary,
            signals=[
                GhostSignalOut(name=s.name, verdict=s.verdict.value, detail=s.detail)
                for s in assessment.signals
            ],
        ),
        description=posting.description,
        ats_vendor=posting.company.ats_vendor,
        ats_job_id=posting.ats_job_id,
        sources=[SourceSighting.model_validate(s) for s in posting.sources],
        first_seen_at=posting.first_seen_at,
        last_seen_at=posting.last_seen_at,
    )


def cycle_counts(session: Session, today: date | None = None) -> list[CycleCount]:
    """Active posting counts per applyable cycle.

    This is the number that answers "is there anything worth applying to right
    now?" for each of Fall 2026, Summer 2027 and the rest.
    """
    today = today or datetime.now(UTC).date()
    cycles = applyable_cycles(today)
    if not cycles:
        return []

    rows = session.execute(
        select(Posting.season, Posting.term_year, func.count(Posting.id))
        .where(Posting.is_active.is_(True), Posting.season.isnot(None))
        .where(_cycle_predicate(cycles))
        .group_by(Posting.season, Posting.term_year)
    ).all()

    by_cycle = {(season, year): count for season, year, count in rows}
    return [
        CycleCount(
            term_label=c.label,
            season=c.season,
            term_year=c.year,
            count=by_cycle.get((c.season, c.year), 0),
        )
        for c in cycles
        if by_cycle.get((c.season, c.year), 0) > 0
    ]


def source_health(session: Session) -> list[SourceHealth]:
    return list(session.scalars(select(SourceHealth).order_by(SourceHealth.source_id)))


def source_breakdown(session: Session) -> dict[str, int]:
    """How many live postings each source currently contributes."""
    rows = session.execute(
        select(PostingSource.source_id, func.count(func.distinct(PostingSource.posting_id)))
        .join(Posting, Posting.id == PostingSource.posting_id)
        .where(Posting.is_active.is_(True))
        .group_by(PostingSource.source_id)
        .order_by(func.count(func.distinct(PostingSource.posting_id)).desc())
    ).all()
    return {source_id: count for source_id, count in rows}
