"""Track endpoints: will my resume parse, and how do I tailor it to this role.

The ATS check is intentionally the most prominent thing here. Getting past the
parser is the precondition for everything else -- a resume the machine mangles
never reaches a human, however good it is.
"""

from __future__ import annotations

import os
import tempfile
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..core import events as event_log
from ..core.corpus import corpus_documents
from ..core.db import get_session
from ..core.models import Application, Posting
from ..discover.match import build_index
from . import applications, ats_check, funnel, resumes, tailor
from .schemas import (
    ApplicationOut,
    ApplicationPatchIn,
    AtsReportOut,
    BoardOut,
    ConversionOut,
    FindingOut,
    FunnelOut,
    HardRequirementOut,
    LogEventIn,
    ParsePreviewOut,
    RequirementOut,
    ResumeVersionIn,
    ResumeVersionOut,
    StageCountOut,
    StageEntryOut,
    TailorReportOut,
    TransitionOut,
    VersionOutcomeOut,
    WaitTimeOut,
)

router = APIRouter(prefix="/api", tags=["track"])

_MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # a resume is never this large; guards abuse


def _ats_report_out(report: ats_check.AtsReport) -> AtsReportOut:
    return AtsReportOut(
        will_parse_cleanly=report.will_parse_cleanly,
        verdict=report.verdict(),
        page_count=report.page_count,
        char_count=report.char_count,
        word_count=report.word_count,
        fonts=report.fonts,
        findings=[
            FindingOut(
                severity=f.severity.name,
                category=f.category,
                title=f.title,
                detail=f.detail,
                fix=f.fix,
                evidence=f.evidence,
            )
            for f in report.sorted_findings()
        ],
        preview=(
            ParsePreviewOut(
                visual_text=report.preview.visual_text,
                ats_text=report.preview.ats_text,
                scrambled=report.preview.scrambled,
                column_count=report.preview.column_count,
            )
            if report.preview
            else None
        ),
    )


@router.post("/resume/check", response_model=AtsReportOut)
async def check_resume(
    file: UploadFile = File(...),
    employment_type_hint: str | None = Form(default="internship"),
) -> AtsReportOut:
    """Analyse an uploaded resume PDF for ATS parse safety.

    Nothing is stored: the file is written to a temp path, analysed, and
    deleted. The operator gets the findings and the parse preview back.
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
        report = ats_check.check_resume(tmp.name, employment_type_hint=employment_type_hint or None)
    finally:
        os.unlink(tmp.name)
    return _ats_report_out(report)


def _req_out(req: tailor.Requirement) -> RequirementOut:
    return RequirementOut(
        term=req.display,
        tier=req.tier.name,
        posting_count=req.posting_count,
        emphasis=req.emphasis,
        is_technical=req.is_technical,
        evidenced=req.evidenced,
        is_reword=req.is_reword,
        in_resume=req.in_resume,
        component_evidence=req.component_evidence,
        advice=req.advice(),
    )


@router.post("/postings/{posting_id}/tailor", response_model=TailorReportOut)
def tailor_to_posting(
    posting_id: UUID,
    resume_text: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> TailorReportOut:
    """Read this posting closely and check it against the operator's corpus.

    ``resume_text`` is optional: without it the report still shows what the
    posting requires and what the corpus can evidence, just not the "already on
    the resume you sent" distinction.
    """
    posting = session.get(Posting, posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail="Posting not found")
    if not posting.description_available:
        raise HTTPException(
            status_code=422,
            detail="This posting has no description to read. "
            "Open it from a source that carries one.",
        )

    index = build_index(corpus_documents(session))
    report = tailor.tailor(
        title=posting.title,
        description=posting.description or "",
        index=index,
        resume_text=resume_text,
        company_name=posting.company.name if posting.company else None,
    )

    return TailorReportOut(
        posting_title=report.posting_title,
        company_name=report.company_name,
        summary=report.summary(),
        coverage=report.coverage(),
        potential_coverage=report.potential_coverage(),
        resume_available=report.resume_available,
        hard_requirements=[
            HardRequirementOut(kind=h.kind, label=h.label, detail=h.detail)
            for h in report.hard_requirements
        ],
        required_gaps=[_req_out(r) for r in report.required_gaps],
        missing_from_resume=[_req_out(r) for r in report.missing_from_resume],
        rewords=[_req_out(r) for r in report.rewords],
        evidenced=[_req_out(r) for r in report.evidenced],
        other_gaps=[_req_out(r) for r in report.gaps if r.tier is not tailor.Tier.REQUIRED],
    )


# --------------------------------------------------------------------------
# The application board
# --------------------------------------------------------------------------


def _application_out(state: applications.ApplicationState, posting: Posting) -> ApplicationOut:
    return ApplicationOut(
        id=state.application_id,
        posting_id=state.posting_id,
        posting_title=posting.title,
        company_name=posting.company.name if posting.company else "—",
        posting_url=posting.url,
        term_label=(
            f"{posting.season.value.title()} {posting.term_year}"
            if posting.season and posting.term_year
            else None
        ),
        location=posting.location_labels[0] if posting.location_labels else None,
        stage=state.stage.name,
        stage_label=applications.STAGE_LABELS[state.stage],
        is_live=state.stage.is_live,
        is_terminal=state.stage.is_terminal,
        timeline=[
            StageEntryOut(
                event_type=e.event_type,
                stage=e.stage.name,
                label=e.label,
                occurred_at=e.occurred_at,
                note=e.note,
            )
            for e in state.timeline
        ],
        notes=state.notes,
        resume_version_id=state.resume_version_id,
        days_silent=state.days_silent(),
        silence_note=state.silence_note(),
        next_events=[
            TransitionOut(event_type=t.event_type, label=t.label, is_setback=t.is_setback)
            for t in applications.transitions_from(state.stage)
        ],
    )


def _funnel_out(report: funnel.FunnelReport) -> FunnelOut:
    return FunnelOut(
        total=report.total,
        has_enough_data=report.has_enough_data,
        basis=report.basis(),
        stages=[
            StageCountOut(stage=s.stage.name, label=s.label, reached=s.reached, current=s.current)
            for s in report.stages
        ],
        conversions=[
            ConversionOut(
                from_label=c.from_label,
                to_label=c.to_label,
                reached_from=c.reached_from,
                reached_to=c.reached_to,
                has_enough_data=c.has_enough_data,
                statement=c.statement,
            )
            for c in report.conversions
        ],
        waits=[
            WaitTimeOut(
                from_label=w.from_label,
                to_label=w.to_label,
                sample_size=w.sample_size,
                median_days=w.median_days,
                statement=w.statement,
            )
            for w in report.waits
        ],
    )


@router.get("/applications", response_model=BoardOut)
def get_board(session: Session = Depends(get_session)) -> BoardOut:
    """Every application, folded from its events, plus the funnel over them."""
    rows = applications.board(session)
    states = [state for state, _ in rows]
    return BoardOut(
        applications=[_application_out(state, posting) for state, posting in rows],
        funnel=_funnel_out(funnel.build(states)),
        resume_versions=[
            ResumeVersionOut.model_validate(v) for v in resumes.list_versions(session)
        ],
        version_outcomes=[
            VersionOutcomeOut(
                version_id=o.version_id,
                label=o.label,
                applied=o.applied,
                responded=o.responded,
                statement=o.statement,
            )
            for o in resumes.outcomes_by_version(session, states)
        ],
    )


# --------------------------------------------------------------------------
# Résumé versions
# --------------------------------------------------------------------------


@router.get("/resume/versions", response_model=list[ResumeVersionOut])
def list_resume_versions(session: Session = Depends(get_session)) -> list[ResumeVersionOut]:
    return [ResumeVersionOut.model_validate(v) for v in resumes.list_versions(session)]


@router.post("/resume/versions", response_model=ResumeVersionOut, status_code=201)
def create_resume_version(
    payload: ResumeVersionIn, session: Session = Depends(get_session)
) -> ResumeVersionOut:
    """Record a résumé the operator sent. Lighthouse tracks and scores; it does
    not generate, so this stores the label and the text, nothing more."""
    try:
        version = resumes.save_version(
            session,
            label=payload.label,
            extracted_text=payload.extracted_text,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return ResumeVersionOut.model_validate(version)


@router.delete("/resume/versions/{version_id}", status_code=204)
def delete_resume_version(version_id: UUID, session: Session = Depends(get_session)) -> None:
    if not resumes.delete_version(session, version_id):
        raise HTTPException(status_code=404, detail="Résumé version not found")
    session.commit()


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
def patch_application(
    application_id: UUID,
    payload: ApplicationPatchIn,
    session: Session = Depends(get_session),
) -> ApplicationOut:
    """Edit the parts of an application that are not dated events.

    Notes and which résumé went out are corrections to a record, not things
    that happened on a date, so they are edits rather than log entries.
    """
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    if payload.notes is not None:
        application.notes = payload.notes.strip() or None
    if payload.clear_resume_version:
        application.resume_version_id = None
    elif payload.resume_version_id is not None:
        try:
            resumes.set_application_version(session, application, payload.resume_version_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    session.commit()
    posting = session.get(Posting, application.posting_id)
    history = event_log.history(session, entity_type=applications.ENTITY, entity_id=application.id)
    return _application_out(applications.fold(application, history), posting)


@router.post("/postings/{posting_id}/apply", response_model=ApplicationOut, status_code=201)
def track_posting(
    posting_id: UUID,
    payload: LogEventIn | None = None,
    session: Session = Depends(get_session),
) -> ApplicationOut:
    """Start tracking a posting, optionally logging a stage in the same call.

    Sending ``{"event_type": "applied"}`` is the one-click apply-and-log path
    from Discover; sending nothing just saves it to the board.
    """
    posting = session.get(Posting, posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail="Posting not found")

    application, _ = applications.get_or_create(session, posting_id, mark_saved=payload is None)
    if payload is not None:
        try:
            applications.log_event(
                session,
                application,
                payload.event_type,
                occurred_at=payload.occurred_at,
                note=payload.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    session.commit()
    history = event_log.history(session, entity_type=applications.ENTITY, entity_id=application.id)
    return _application_out(applications.fold(application, history), posting)


@router.post("/applications/{application_id}/events", response_model=ApplicationOut)
def log_application_event(
    application_id: UUID,
    payload: LogEventIn,
    session: Session = Depends(get_session),
) -> ApplicationOut:
    """Record a stage change. Nothing is overwritten — this appends a fact."""
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        applications.log_event(
            session,
            application,
            payload.event_type,
            occurred_at=payload.occurred_at,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session.commit()
    posting = session.get(Posting, application.posting_id)
    history = event_log.history(session, entity_type=applications.ENTITY, entity_id=application.id)
    return _application_out(applications.fold(application, history), posting)


@router.delete("/applications/{application_id}", status_code=204)
def untrack(application_id: UUID, session: Session = Depends(get_session)) -> None:
    """Remove an application from the board.

    Deliberately rare and explicit: the board is a record, and the usual way to
    close something out is to log ``rejected`` or ``withdrawn`` so the funnel
    keeps the fact that it happened.
    """
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    # The events go too. `events` has no foreign key to `applications` by
    # design — the log outlives what it describes — so nothing cascades, and
    # untracking means "this was a mistake, forget it" rather than "this ended".
    event_log.discard(session, entity_type=applications.ENTITY, entity_id=application.id)
    session.delete(application)
    session.commit()
