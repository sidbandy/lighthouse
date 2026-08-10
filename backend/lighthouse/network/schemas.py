"""API shapes for the networking module."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ContactIn(BaseModel):
    name: str
    company_name: str | None = None
    role_title: str | None = None
    relationship_type: str = Field(
        default="cold", description="cold | warm_intro | alumni | met_at_event | referred_by"
    )
    school: str | None = None
    grad_year: int | None = None
    strength: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="The operator's own read of how well they know this person. "
        "Never computed — a strength derived from message counts would be invented.",
    )
    email: str | None = None
    profile_url: str | None = None
    notes: str | None = None


class InteractionOut(BaseModel):
    id: UUID
    kind: str
    label: str
    direction: str
    summary: str
    channel: str | None = None
    application_id: UUID | None = None
    occurred_at: datetime


class NextStepOut(BaseModel):
    """One thing worth doing, on a real date rather than a priority score."""

    action: str
    due_on: date
    reason: str
    draft_kind: str
    status: str = Field(description="'today', 'in 4 days', '3 days late'. Render as-is.")
    is_due: bool


class ContactOut(BaseModel):
    id: UUID
    name: str
    company_name: str | None = None
    company_id: UUID | None = None
    role_title: str | None = None
    relationship_type: str
    school: str | None = None
    grad_year: int | None = None
    strength: int | None = None
    email: str | None = None
    profile_url: str | None = None
    notes: str | None = None
    is_alumni: bool = False

    stage: str
    stage_label: str
    days_since_outbound: int | None = None
    silence_note: str | None = None
    unanswered_outreach: int = 0
    referral_asked: bool = False
    referral_confirmed: bool = False

    timeline: list[InteractionOut] = []
    next_step: NextStepOut | None = None
    cadence_note: str = ""


class InteractionIn(BaseModel):
    kind: str = Field(description="outreach | reply | conversation | referral_asked | …")
    summary: str = ""
    channel: str | None = None
    direction: str | None = Field(
        default=None, description="Defaults from the kind; a reply is inbound."
    )
    occurred_at: datetime | None = None
    application_id: UUID | None = None


class QueueItemOut(BaseModel):
    contact_id: UUID
    name: str
    company_name: str | None = None
    step: NextStepOut


class CompanyCoverageOut(BaseModel):
    company_id: UUID | None = None
    company_name: str
    contact_count: int
    alumni_count: int
    open_postings: int
    is_target: bool
    note: str


class NetworkOverviewOut(BaseModel):
    school: str | None = None
    total_contacts: int
    alumni_contacts: int
    note: str
    coverage: list[CompanyCoverageOut] = []
    queue: list[QueueItemOut] = []


class ParsedContactOut(BaseModel):
    """A candidate from a pasted block. No id — nothing has been saved."""

    name: str
    role_title: str | None = None
    company_name: str | None = None


class PasteIn(BaseModel):
    text: str
    school: str | None = Field(
        default=None,
        description="Set when the paste came from an alumni search, which marks "
        "the whole batch as alumni.",
    )


class DraftOut(BaseModel):
    variant: str
    subject: str
    body: str
    word_count: int
    source_fact_ids: list[UUID]
    provider: str
    is_fallback: bool = Field(
        description="A template rather than a model. Surfaced because they are "
        "different things and the operator should know which they got."
    )
    grounding_note: str
    warnings: list[str] = []


class RouteOutcomeOut(BaseModel):
    route: str
    applied: int
    responded: int
    statement: str


class ReferralReportOut(BaseModel):
    referred: RouteOutcomeOut
    cold: RouteOutcomeOut
    is_comparable: bool
    note: str
