"""Briefing endpoints: the week in one place.

Transport only. Every figure here was computed by the module that owns it --
cadence, the board, SRS, the story bank -- and the briefing's whole job is
ordering and honest empties, so this router adds nothing but serialisation.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.db import get_session
from . import weekly
from .schemas import (
    BriefItemOut,
    BriefSectionOut,
    TriageGroupOut,
    TriageOut,
    WeeklyBriefOut,
)

router = APIRouter(prefix="/api/briefing", tags=["briefing"])


def _item_out(item: weekly.BriefItem) -> BriefItemOut:
    return BriefItemOut(
        kind=item.kind,
        title=item.title,
        detail=item.detail,
        link=item.link,
        due_on=item.due_on,
        is_late=item.is_late,
    )


def _section_out(section: weekly.BriefSection) -> BriefSectionOut:
    return BriefSectionOut(
        key=section.key,
        title=section.title,
        items=[_item_out(i) for i in section.items],
        count=section.count,
        empty_note=section.empty_note,
    )


@router.get("/weekly", response_model=WeeklyBriefOut)
def weekly_brief(
    session: Session = Depends(get_session),
    today: date | None = Query(
        default=None, description="Override the reference date. Testing and back-dating."
    ),
) -> WeeklyBriefOut:
    """Everything due this week, in the order it should be worked."""
    brief = weekly.build(session, today=today)
    return WeeklyBriefOut(
        generated_for=brief.generated_for,
        headline=brief.headline(),
        total_items=brief.total_items,
        late_items=sum(1 for s in brief.sections for i in s.items if i.is_late),
        sections=[_section_out(s) for s in brief.sections],
        funnel_note=brief.funnel_note,
        baseline_note=brief.baseline_note,
    )


@router.get("/triage", response_model=list[TriageGroupOut])
def triage(
    session: Session = Depends(get_session),
    today: date | None = Query(default=None),
) -> list[TriageGroupOut]:
    """Live applications sorted into deep / standard / light.

    Grouped rather than returned flat, because the bands are the point: a list
    the operator has to re-sort in their head is the thing this replaces. Empty
    bands are kept so the shape is stable and "nothing deserves deep work right
    now" is visible rather than absent.
    """
    rows = weekly.triage(session, today=today)
    return [
        TriageGroupOut(
            band=band,
            blurb=weekly.BAND_BLURB[band],
            applications=[
                TriageOut(
                    application_id=t.application_id,
                    posting_title=t.posting_title,
                    company_name=t.company_name,
                    band=t.band,
                    band_blurb=weekly.BAND_BLURB[t.band],
                    reason=t.reason,
                    stage_label=t.stage_label,
                )
                for t in rows
                if t.band == band
            ],
            count=sum(1 for t in rows if t.band == band),
        )
        for band in weekly.BANDS
    ]
