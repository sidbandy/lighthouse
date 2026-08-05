"""Corpus and onboarding endpoints.

Extraction and commitment are separate calls: ``/corpus/extract`` returns drafts
and saves nothing, ``/corpus/facts/bulk`` saves what the operator kept. Corpus
writes invalidate the match index so the next score reflects the edit.
"""

from __future__ import annotations

import os
import tempfile
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..discover import coverage as coverage_service
from ..discover import ranking
from ..discover.lanes import selectivity_of
from . import corpus as corpus_service
from . import onboarding as onboarding_service
from .db import get_session
from .models import Company, Posting
from .schemas import (
    CompanySuggestionOut,
    ConstraintsIn,
    ConstraintsOut,
    CorpusOut,
    CorpusSummaryOut,
    CoverageOut,
    DraftFactOut,
    ExtractionOut,
    FactContributionOut,
    FactIn,
    FactOut,
    OnboardingOut,
    TargetCompanyOut,
    TermDemandOut,
)

router = APIRouter(prefix="/api", tags=["corpus"])

_MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def _summary_out(summary: corpus_service.CorpusSummary) -> CorpusSummaryOut:
    return CorpusSummaryOut(
        fact_count=summary.fact_count,
        facts_by_type=summary.facts_by_type,
        story_count=summary.story_count,
        unverified_story_count=summary.unverified_story_count,
        is_usable_for_matching=summary.is_usable_for_matching,
        readiness_note=summary.readiness_note,
    )


def _fact_input(payload: FactIn) -> corpus_service.FactInput:
    return corpus_service.FactInput(
        fact_type=payload.fact_type,
        title=payload.title,
        body=payload.body,
        metadata=payload.metadata,
    )


def _committed(session: Session) -> None:
    """Commit, then drop the cached match and market indexes.

    Both are keyed on corpus/posting state, so they would eventually notice --
    but "eventually" means the operator adds a project and sees an unchanged
    score, which reads as the app ignoring them.
    """
    session.commit()
    ranking.invalidate_cache()


# --------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------


@router.get("/corpus", response_model=CorpusOut)
def get_corpus(
    session: Session = Depends(get_session),
    fact_type: str | None = Query(default=None),
) -> CorpusOut:
    """Every fact the operator has, plus a read on how usable the corpus is."""
    facts = corpus_service.list_facts(session, fact_type=fact_type)
    return CorpusOut(
        facts=[FactOut.model_validate(f) for f in facts],
        summary=_summary_out(corpus_service.summarize(session)),
    )


@router.post("/corpus/facts", response_model=FactOut, status_code=201)
def create_fact(payload: FactIn, session: Session = Depends(get_session)) -> FactOut:
    try:
        fact = corpus_service.add_fact(session, _fact_input(payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _committed(session)
    return FactOut.model_validate(fact)


@router.patch("/corpus/facts/{fact_id}", response_model=FactOut)
def edit_fact(fact_id: UUID, payload: FactIn, session: Session = Depends(get_session)) -> FactOut:
    try:
        fact = corpus_service.update_fact(session, fact_id, _fact_input(payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    _committed(session)
    return FactOut.model_validate(fact)


@router.delete("/corpus/facts/{fact_id}", status_code=204)
def remove_fact(fact_id: UUID, session: Session = Depends(get_session)) -> None:
    if not corpus_service.delete_fact(session, fact_id):
        raise HTTPException(status_code=404, detail="Fact not found")
    _committed(session)


@router.post("/corpus/facts/bulk", response_model=list[FactOut], status_code=201)
def create_facts(payload: list[FactIn], session: Session = Depends(get_session)) -> list[FactOut]:
    """Commit a reviewed batch -- the drafts the operator kept after extraction.

    All or nothing: a batch that is half-written is worse than one that failed,
    because the operator cannot tell which half.
    """
    if not payload:
        raise HTTPException(status_code=422, detail="No facts to save.")
    try:
        facts = onboarding_service.commit_reviewed_facts(session, [_fact_input(p) for p in payload])
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _committed(session)
    return [FactOut.model_validate(f) for f in facts]


@router.post("/corpus/extract", response_model=ExtractionOut)
async def extract_resume(file: UploadFile = File(...)) -> ExtractionOut:
    """Read a resume PDF into draft facts. **Nothing is saved.**

    The operator reviews, edits and discards before any of this becomes a fact,
    which is the whole point: an extracted bullet is a guess about what they
    did, and the corpus may only contain things they actually did.
    """
    contents = await file.read()
    if len(contents) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large.")
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file.")

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(contents)
        tmp.close()
        extracted = onboarding_service.draft_facts_from_resume(tmp.name)
    except Exception as exc:  # pdfplumber raises a variety of parse errors
        raise HTTPException(status_code=422, detail=f"Could not read that PDF: {exc}") from exc
    finally:
        os.unlink(tmp.name)

    if extracted.likely_image_based:
        note = (
            "Almost no text came out of this PDF, which usually means it is a scan or an "
            "image. An ATS would extract nothing from it either — that is worth fixing "
            "before anything else."
        )
    elif not extracted.facts:
        note = (
            "The text extracted, but no section headings were recognised, so nothing could "
            "be split into facts. Add them by hand below."
        )
    else:
        note = (
            f"{len(extracted.facts)} draft facts. Nothing is saved yet — edit or remove "
            "anything that is not accurate, then save the ones you keep."
        )

    return ExtractionOut(
        drafts=[
            DraftFactOut(fact_type=f.fact_type, title=f.title, body=f.body) for f in extracted.facts
        ],
        page_count=extracted.page_count,
        char_count=extracted.char_count,
        likely_image_based=extracted.likely_image_based,
        note=note,
    )


# --------------------------------------------------------------------------
# Coverage: what the corpus is worth in the live market
# --------------------------------------------------------------------------


def _demand_out(demand: coverage_service.TermDemand) -> TermDemandOut:
    return TermDemandOut(
        term=demand.display,
        posting_count=demand.posting_count,
        core_count=demand.core_count,
        is_technical=demand.is_technical,
    )


@router.get("/corpus/coverage", response_model=CoverageOut)
def get_coverage(
    session: Session = Depends(get_session),
    role_family: list[str] = Query(default=[]),
    gap_limit: int = Query(default=25, ge=1, le=100),
) -> CoverageOut:
    """What each fact is worth against the postings currently ingested.

    Every number is an observed count over the stated sample of postings that
    carry a real description. Nothing here is predicted or fitted.
    """
    report = coverage_service.corpus_coverage(
        session, role_families=tuple(sorted(set(role_family))), gap_limit=gap_limit
    )
    return CoverageOut(
        sample_size=report.sample_size,
        is_meaningful=report.is_meaningful,
        basis=report.basis(),
        fact_count=report.fact_count,
        reached=report.reached,
        unreached=report.unreached,
        contributions=[
            FactContributionOut(
                fact_id=UUID(c.fact_id),
                fact_type=c.fact_type,
                title=c.title,
                terms=[_demand_out(t) for t in c.terms],
                reach=c.reach,
                unique_reach=c.unique_reach,
                unmatched_term_count=c.unmatched_term_count,
            )
            for c in report.contributions
        ],
        gaps=[_demand_out(g) for g in report.gaps],
    )


# --------------------------------------------------------------------------
# Onboarding
# --------------------------------------------------------------------------


def _target_out(company: Company) -> TargetCompanyOut:
    return TargetCompanyOut(
        id=company.id,
        name=company.name,
        canonical_name=company.canonical_name,
        tier=company.tier,
        selectivity=selectivity_of(company.canonical_name, company.tier),
    )


def _onboarding_out(session: Session) -> OnboardingOut:
    constraints = onboarding_service.load_constraints(session)
    state = onboarding_service.onboarding_state(session, constraints=constraints)
    return OnboardingOut(
        next_step=state.next_step,
        is_complete=state.is_complete,
        corpus=_summary_out(state.corpus),
        target_company_count=state.target_company_count,
        constraints_set=state.constraints_set,
        constraints=(
            ConstraintsOut(**onboarding_service.constraints_to_dict(constraints))
            if constraints
            else None
        ),
        targets=[_target_out(c) for c in onboarding_service.target_companies(session)],
    )


@router.get("/onboarding", response_model=OnboardingOut)
def get_onboarding(session: Session = Depends(get_session)) -> OnboardingOut:
    """Where setup stands, and the one thing to do next."""
    return _onboarding_out(session)


@router.put("/onboarding/constraints", response_model=OnboardingOut)
def put_constraints(
    payload: ConstraintsIn, session: Session = Depends(get_session)
) -> OnboardingOut:
    try:
        onboarding_service.save_constraints(
            session,
            onboarding_service.OperatorConstraints(
                preferred_locations=payload.preferred_locations,
                open_to_remote=payload.open_to_remote,
                sponsorship=payload.sponsorship,
                weekly_study_hours=payload.weekly_study_hours,
                target_cycles=payload.target_cycles,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _onboarding_out(session)


@router.put("/onboarding/targets", response_model=OnboardingOut)
def put_targets(names: list[str], session: Session = Depends(get_session)) -> OnboardingOut:
    """Replace the set of target companies.

    Marking a target says nothing about how hard the company is to get into --
    that is ``Company.tier`` and this endpoint never touches it. Wanting a job
    has never made it easier to get.
    """
    onboarding_service.set_target_companies(session, names)
    session.commit()
    return _onboarding_out(session)


@router.get("/companies/search", response_model=list[CompanySuggestionOut])
def search_companies(
    session: Session = Depends(get_session),
    q: str = Query(default="", description="Prefix or substring of the company name."),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[CompanySuggestionOut]:
    """Companies to pick targets from, ranked by how many live postings they
    have -- so the operator picks against real supply rather than memory."""
    counts = (
        select(Posting.company_id, func.count(Posting.id).label("n"))
        .where(Posting.is_active.is_(True))
        .group_by(Posting.company_id)
        .subquery()
    )
    stmt = (
        select(Company, func.coalesce(counts.c.n, 0).label("posting_count"))
        .outerjoin(counts, counts.c.company_id == Company.id)
        .order_by(func.coalesce(counts.c.n, 0).desc(), Company.name)
        .limit(limit)
    )
    if q.strip():
        stmt = stmt.where(Company.canonical_name.contains(q.strip().lower()))

    already = {c.id for c in onboarding_service.target_companies(session)}

    return [
        CompanySuggestionOut(
            name=company.name,
            canonical_name=company.canonical_name,
            posting_count=int(count),
            is_target=company.id in already,
        )
        for company, count in session.execute(stmt)
    ]
