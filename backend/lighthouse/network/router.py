"""Networking endpoints.

Capture and commitment are separate calls, the same split the corpus uses:
``/network/parse`` reads a pasted block and saves nothing, ``/network/contacts/bulk``
writes the ones the operator kept. Drafting is a third call that also writes
nothing -- Lighthouse never sends a message, and never stores one as though it
had been sent.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.db import get_session
from ..core.models import Contact
from ..track import applications as track_applications
from . import alumni, cadence, capture, drafts, referrals
from . import contacts as contacts_service
from .schemas import (
    CompanyCoverageOut,
    ContactIn,
    ContactOut,
    DraftOut,
    InteractionIn,
    InteractionOut,
    NetworkOverviewOut,
    NextStepOut,
    ParsedContactOut,
    PasteIn,
    QueueItemOut,
    ReferralReportOut,
    RouteOutcomeOut,
)

router = APIRouter(prefix="/api/network", tags=["network"])


def _next_step_out(step: cadence.NextStep, today: date | None = None) -> NextStepOut:
    return NextStepOut(
        action=step.action,
        due_on=step.due_on,
        reason=step.reason,
        draft_kind=step.draft_kind,
        status=step.status(today),
        is_due=step.is_due(today),
    )


def _contact_out(
    contact: Contact,
    state: contacts_service.ContactState,
    *,
    school: str | None = None,
    today: date | None = None,
) -> ContactOut:
    plan = cadence.next_step_for(state, today=today)
    return ContactOut(
        id=contact.id,
        name=contact.name,
        company_name=contact.company_name,
        company_id=contact.company_id,
        role_title=contact.role_title,
        relationship_type=contact.relationship_type,
        school=contact.school,
        grad_year=contact.grad_year,
        strength=contact.strength,
        email=contact.email,
        profile_url=contact.profile_url,
        notes=contact.notes,
        is_alumni=alumni.is_alumni(contact, school),
        stage=state.stage.value,
        stage_label=contacts_service.STAGE_LABELS[state.stage],
        days_since_outbound=state.days_since_last_outbound(today),
        silence_note=state.silence_note(today),
        unanswered_outreach=state.unanswered_outreach,
        referral_asked=state.referral_asked,
        referral_confirmed=state.referral_confirmed,
        timeline=[
            InteractionOut(
                id=e.id,
                kind=e.kind.value,
                label=e.label,
                direction=e.direction,
                summary=e.summary,
                channel=e.channel,
                application_id=e.application_id,
                occurred_at=e.occurred_at,
            )
            for e in state.timeline
        ],
        next_step=_next_step_out(plan.next_step, today) if plan.next_step else None,
        cadence_note=plan.note,
    )


def _input(payload: ContactIn) -> contacts_service.ContactInput:
    return contacts_service.ContactInput(
        name=payload.name,
        company_name=payload.company_name,
        role_title=payload.role_title,
        relationship_type=payload.relationship_type,
        school=payload.school,
        grad_year=payload.grad_year,
        strength=payload.strength,
        email=payload.email,
        profile_url=payload.profile_url,
        notes=payload.notes,
    )


@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(
    session: Session = Depends(get_session), today: date | None = None
) -> list[ContactOut]:
    """Every contact, folded, most recent activity first."""
    school = alumni.overview(session).school
    return [
        _contact_out(contact, state, school=school, today=today)
        for contact, state in contacts_service.list_contacts(session)
    ]


@router.post("/contacts", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactIn, session: Session = Depends(get_session)) -> ContactOut:
    try:
        contact = contacts_service.add_contact(session, _input(payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _contact_out(contact, contacts_service.fold(contact, []))


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def edit_contact(
    contact_id: UUID, payload: ContactIn, session: Session = Depends(get_session)
) -> ContactOut:
    try:
        contact = contacts_service.update_contact(session, contact_id, _input(payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    session.commit()
    return _contact_out(contact, contacts_service.fold(contact, contact.interactions))


@router.delete("/contacts/{contact_id}", status_code=204)
def remove_contact(contact_id: UUID, session: Session = Depends(get_session)) -> None:
    if not contacts_service.delete_contact(session, contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    session.commit()


@router.post("/contacts/{contact_id}/interactions", response_model=ContactOut, status_code=201)
def log_interaction(
    contact_id: UUID, payload: InteractionIn, session: Session = Depends(get_session)
) -> ContactOut:
    """Record an exchange. Appends a dated fact; nothing is overwritten."""
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    try:
        contacts_service.log_interaction(
            session,
            contact,
            payload.kind,
            summary=payload.summary,
            channel=payload.channel,
            direction=payload.direction,
            occurred_at=payload.occurred_at,
            application_id=payload.application_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    session.refresh(contact)
    return _contact_out(contact, contacts_service.fold(contact, contact.interactions))


@router.post("/parse", response_model=list[ParsedContactOut])
def parse_paste(payload: PasteIn) -> list[ParsedContactOut]:
    """Read a pasted block into candidates. **Nothing is saved.**

    The paste comes from LinkedIn's own Alumni tool, which is a first-party
    feature built for this. Lighthouse fetches nothing and touches no account.
    """
    return [
        ParsedContactOut(name=c.name, role_title=c.role_title, company_name=c.company_name)
        for c in capture.parse_pasted_contacts(payload.text)
    ]


@router.post("/contacts/bulk", response_model=list[ContactOut], status_code=201)
def create_contacts(
    payload: list[ContactIn], session: Session = Depends(get_session)
) -> list[ContactOut]:
    """Commit the candidates the operator kept after a paste."""
    if not payload:
        raise HTTPException(status_code=422, detail="No contacts to save.")
    created = []
    try:
        for item in payload:
            created.append(contacts_service.add_contact(session, _input(item)))
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return [_contact_out(c, contacts_service.fold(c, [])) for c in created]


@router.get("/overview", response_model=NetworkOverviewOut)
def overview(
    session: Session = Depends(get_session),
    today: date | None = None,
    horizon_days: int = Query(default=0, ge=0, le=90),
) -> NetworkOverviewOut:
    """Where the network is thin, and what is due.

    Target companies with nobody at them lead: that is the list an hour on the
    alumni page can actually change.
    """
    report = alumni.overview(session)
    rows = contacts_service.list_contacts(session)
    queue = cadence.due_queue(rows, today=today, horizon_days=horizon_days)
    return NetworkOverviewOut(
        school=report.school,
        total_contacts=report.total_contacts,
        alumni_contacts=report.alumni_contacts,
        note=report.note(),
        coverage=[
            CompanyCoverageOut(
                company_id=c.company_id,
                company_name=c.company_name,
                contact_count=c.contact_count,
                alumni_count=c.alumni_count,
                open_postings=c.open_postings,
                is_target=c.is_target,
                note=c.note(),
            )
            for c in report.coverage
        ],
        queue=[
            QueueItemOut(
                contact_id=UUID(item.contact_id),
                name=item.name,
                company_name=item.company_name,
                step=_next_step_out(item.step, today),
            )
            for item in queue
        ],
    )


@router.post("/contacts/{contact_id}/drafts", response_model=list[DraftOut])
def draft(
    contact_id: UUID,
    kind: str = Query(default="cold_outreach"),
    session: Session = Depends(get_session),
) -> list[DraftOut]:
    """Two drafts to choose between. **Nothing is sent, and nothing is stored.**

    Refuses outright when the corpus is empty: a message about the operator with
    nothing real behind it is the one artifact this project will not produce.
    """
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    try:
        written = drafts.draft_messages(session, contact, kind=kind)
    except drafts.CannotDraft as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return [
        DraftOut(
            variant=d.variant,
            subject=d.subject,
            body=d.body,
            word_count=d.word_count,
            source_fact_ids=d.source_fact_ids,
            provider=d.provider,
            is_fallback=d.is_fallback,
            grounding_note=d.grounding_note,
            warnings=d.warnings,
        )
        for d in written
    ]


@router.get("/referrals", response_model=ReferralReportOut)
def referral_split(session: Session = Depends(get_session)) -> ReferralReportOut:
    """Referred applications against cold ones. Counts, with the sample shown."""
    states = [state for state, _ in track_applications.board(session)]
    report = referrals.build(states, referrals.referred_application_ids(session))
    return ReferralReportOut(
        referred=RouteOutcomeOut(
            route=report.referred.route,
            applied=report.referred.applied,
            responded=report.referred.responded,
            statement=report.referred.statement,
        ),
        cold=RouteOutcomeOut(
            route=report.cold.route,
            applied=report.cold.applied,
            responded=report.cold.responded,
            statement=report.cold.statement,
        ),
        is_comparable=report.is_comparable,
        note=report.note(),
    )
