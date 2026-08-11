"""Study endpoints: what to practise, what to review, and what else to learn."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.db import get_session
from . import attempts as attempts_service
from . import company_delta, curriculum, srs
from .catalog import PATTERNS, TOPICS_BY_SLUG

router = APIRouter(prefix="/api/study", tags=["study"])


class ResourceOut(BaseModel):
    label: str
    url: str
    kind: str
    note: str = ""
    is_free: bool = True


class PatternRecordOut(BaseModel):
    slug: str
    name: str
    blurb: str
    total: int
    clean: int
    has_enough: bool = Field(
        description="Below the sample floor a pattern is not weak, it is unmeasured."
    )
    is_weak: bool
    is_untouched: bool
    days_since: int | None = None
    statement: str
    resources: list[ResourceOut] = []


class ProblemOut(BaseModel):
    slug: str
    title: str
    difficulty: str
    url: str
    patterns: list[str]
    is_core: bool


class SuggestionOut(BaseModel):
    problem: ProblemOut
    pattern_slug: str
    pattern_name: str
    reason: str


class ReviewOut(BaseModel):
    problem_slug: str
    title: str
    url: str
    step: int
    due_on: date
    days_overdue: int
    statement: str


class ReviewQueueOut(BaseModel):
    due: list[ReviewOut] = []
    upcoming: list[ReviewOut] = []
    total_due: int = 0
    was_capped: bool = False
    note: str


class TopicNeedOut(BaseModel):
    slug: str
    name: str
    blurb: str
    application_count: int
    total_applications: int
    matched_terms: list[str]
    companies: list[str]
    partially_covered: bool
    statement: str
    hours_low: int
    hours_high: int
    resources: list[ResourceOut]


class CurriculumOut(BaseModel):
    total_applications: int
    note: str
    needs: list[TopicNeedOut] = []
    uncatalogued: list[tuple[str, int]] = Field(
        default=[],
        description="Terms your applications emphasise that the catalogue does not cover. "
        "Shown rather than swallowed — the catalogue is hand-maintained and always behind.",
    )


class StudyHomeOut(BaseModel):
    patterns: list[PatternRecordOut]
    suggestions: list[SuggestionOut]
    reviews: ReviewQueueOut
    curriculum: CurriculumOut
    prerequisite_gaps: list[str] = []


class AttemptIn(BaseModel):
    problem_slug: str
    outcome: str = Field(description="solved_clean | solved_with_hint | solved_over_time | failed")
    time_taken_sec: int | None = None
    attempted_at: datetime | None = None
    notes: str | None = None
    pattern_tags: list[str] | None = None


class PatternDemandOut(BaseModel):
    slug: str
    name: str
    report_count: int
    percent: int


class CompanyDeltaOut(BaseModel):
    company_name: str
    report_count: int
    coverage_quality: str = Field(description="rich | partial | none — always rendered.")
    note: str
    demand: list[PatternDemandOut] = []
    leverage: list[str] = []


def _resources(items) -> list[ResourceOut]:
    return [
        ResourceOut(label=r.label, url=r.url, kind=r.kind, note=r.note, is_free=r.is_free)
        for r in items
    ]


def _record_out(record, today: date | None = None) -> PatternRecordOut:
    return PatternRecordOut(
        slug=record.slug,
        name=record.pattern.name,
        blurb=record.pattern.blurb,
        total=record.total,
        clean=record.clean,
        has_enough=record.has_enough,
        is_weak=record.is_weak,
        is_untouched=record.is_untouched,
        days_since=record.days_since(today),
        statement=record.statement(today),
        resources=_resources(record.pattern.resources),
    )


def _problem_out(problem) -> ProblemOut:
    return ProblemOut(
        slug=problem.slug,
        title=problem.title,
        difficulty=problem.difficulty,
        url=problem.url,
        patterns=list(problem.patterns),
        is_core=problem.is_core,
    )


def _queue_out(queue, today: date | None = None) -> ReviewQueueOut:
    def out(review) -> ReviewOut:
        return ReviewOut(
            problem_slug=review.problem_slug,
            title=review.title,
            url=review.url,
            step=review.step,
            due_on=review.due_on,
            days_overdue=review.days_overdue(today),
            statement=review.statement(today),
        )

    return ReviewQueueOut(
        due=[out(r) for r in queue.due],
        upcoming=[out(r) for r in queue.upcoming],
        total_due=queue.total_due,
        was_capped=queue.was_capped,
        note=queue.note(),
    )


def _curriculum_out(built) -> CurriculumOut:
    return CurriculumOut(
        total_applications=built.total_applications,
        note=built.note(),
        needs=[
            TopicNeedOut(
                slug=n.slug,
                name=n.topic.name,
                blurb=n.topic.blurb,
                application_count=n.application_count,
                total_applications=n.total_applications,
                matched_terms=n.matched_terms,
                companies=n.companies,
                partially_covered=n.partially_covered,
                statement=n.statement(),
                hours_low=n.topic.hours_low,
                hours_high=n.topic.hours_high,
                resources=_resources(n.resources),
            )
            for n in built.needs
        ],
        uncatalogued=built.uncatalogued,
    )


def _build_home(
    session: Session, *, today: date | None = None, suggestions: int = 6
) -> StudyHomeOut:
    """Assemble the study page.

    A plain function rather than a route, because two endpoints need it and
    calling a route function directly hands you the raw ``Query`` object instead
    of its default -- which fails at the first comparison, at runtime, in the
    one path a type checker cannot see.
    """
    records = attempts_service.records(session)
    return StudyHomeOut(
        patterns=[_record_out(r, today) for r in records],
        suggestions=[
            SuggestionOut(
                problem=_problem_out(s.problem),
                pattern_slug=s.pattern.slug,
                pattern_name=s.pattern.name,
                reason=s.reason,
            )
            for s in attempts_service.next_problems(session, limit=suggestions, today=today)
        ],
        reviews=_queue_out(srs.build_queue(session, today=today), today),
        curriculum=_curriculum_out(curriculum.build(session)),
        prerequisite_gaps=attempts_service.prerequisite_gaps(session),
    )


@router.get("", response_model=StudyHomeOut)
def study_home(
    session: Session = Depends(get_session),
    today: date | None = None,
    suggestions: int = Query(default=6, ge=1, le=20),
) -> StudyHomeOut:
    """Everything the study page needs, in one call.

    The pattern record, what to attempt next at the operator's actual level,
    what is due for review, and what their own applications say they should be
    learning besides algorithms.
    """
    return _build_home(session, today=today, suggestions=suggestions)


@router.post("/attempts", response_model=StudyHomeOut, status_code=201)
def log_attempt(
    payload: AttemptIn,
    session: Session = Depends(get_session),
    today: date | None = None,
) -> StudyHomeOut:
    """Record one attempt, and hand back the re-derived page.

    Everything downstream — the record, what to try next, the review schedule —
    is folded from the attempt log, so one write changes all of it at once.
    """
    try:
        attempts_service.log_attempt(
            session,
            problem_slug=payload.problem_slug,
            outcome=payload.outcome,
            pattern_tags=payload.pattern_tags,
            time_taken_sec=payload.time_taken_sec,
            attempted_at=payload.attempted_at,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _build_home(session, today=today)


@router.get("/patterns", response_model=list[PatternRecordOut])
def list_patterns(
    session: Session = Depends(get_session), today: date | None = None
) -> list[PatternRecordOut]:
    return [_record_out(r, today) for r in attempts_service.records(session)]


@router.get("/patterns/{pattern_slug}/problems", response_model=list[ProblemOut])
def pattern_problems(pattern_slug: str) -> list[ProblemOut]:
    from .catalog import problems_for

    if pattern_slug not in {p.slug for p in PATTERNS}:
        raise HTTPException(status_code=404, detail="Unknown pattern")
    return [_problem_out(p) for p in problems_for(pattern_slug)]


@router.get("/topics/{topic_slug}", response_model=TopicNeedOut | None)
def topic(topic_slug: str, session: Session = Depends(get_session)) -> TopicNeedOut | None:
    """One topic with the operator's own evidence for studying it."""
    if topic_slug not in TOPICS_BY_SLUG:
        raise HTTPException(status_code=404, detail="Unknown topic")
    built = curriculum.build(session)
    for need in built.needs:
        if need.slug == topic_slug:
            return _curriculum_out(built).needs[built.needs.index(need)]
    return None


@router.get("/companies/{company_id}/delta", response_model=CompanyDeltaOut)
def company_pattern_delta(
    company_id: UUID, session: Session = Depends(get_session), today: date | None = None
) -> CompanyDeltaOut:
    """What this company reportedly asks, crossed with the operator's record.

    Returns an honest "no reports" until Company Intelligence populates
    ``reported_questions``. A confident-looking distribution built from nothing
    is the one output this endpoint must never produce.
    """
    delta = company_delta.build(session, company_id, today=today)
    return CompanyDeltaOut(
        company_name=delta.company_name,
        report_count=delta.report_count,
        coverage_quality=delta.coverage_quality,
        note=delta.note(),
        demand=[
            PatternDemandOut(
                slug=d.slug, name=d.name, report_count=d.report_count, percent=d.percent
            )
            for d in delta.demand
        ],
        leverage=delta.leverage_statements(),
    )
