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

from ..core.corpus import corpus_documents
from ..core.db import get_session
from ..core.models import Posting
from ..discover.match import build_index
from . import ats_check, tailor
from .schemas import (
    AtsReportOut,
    FindingOut,
    HardRequirementOut,
    ParsePreviewOut,
    RequirementOut,
    TailorReportOut,
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
