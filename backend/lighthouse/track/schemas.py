"""API shapes for the Track module: ATS check, tailoring, and the application board."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FindingOut(BaseModel):
    """One ATS parse problem, ranked by how likely it is to cause a rejection."""

    severity: str = Field(description="'CRITICAL', 'WARNING', or 'MINOR'.")
    category: str
    title: str
    detail: str
    fix: str
    evidence: str | None = None


class ParsePreviewOut(BaseModel):
    """What the operator laid out vs what a naive ATS extracts. When
    ``scrambled`` is true, ``ats_text`` is the demonstration of the problem."""

    visual_text: str
    ats_text: str
    scrambled: bool
    column_count: int


class AtsReportOut(BaseModel):
    will_parse_cleanly: bool
    verdict: str
    page_count: int
    char_count: int
    word_count: int
    fonts: list[str]
    findings: list[FindingOut]
    preview: ParsePreviewOut | None = None


class HardRequirementOut(BaseModel):
    kind: str
    label: str
    detail: str


class RequirementOut(BaseModel):
    term: str
    tier: str = Field(description="'REQUIRED', 'PREFERRED', 'RESPONSIBILITY', or 'GENERAL'.")
    posting_count: int
    emphasis: str
    is_technical: bool
    evidenced: bool
    is_reword: bool
    in_resume: bool
    component_evidence: list[str]
    advice: str


class TailorReportOut(BaseModel):
    posting_title: str
    company_name: str | None
    summary: str
    coverage: int
    potential_coverage: int
    resume_available: bool
    hard_requirements: list[HardRequirementOut]
    # Grouped for the UI, worst/most-actionable first.
    required_gaps: list[RequirementOut]
    missing_from_resume: list[RequirementOut]
    rewords: list[RequirementOut]
    evidenced: list[RequirementOut]
    other_gaps: list[RequirementOut]


# --------------------------------------------------------------------------
# Résumé versions
# --------------------------------------------------------------------------


class ResumeVersionIn(BaseModel):
    label: str = Field(description="What the operator calls it, e.g. 'v3 — security lead'.")
    extracted_text: str = ""
    notes: str | None = None


class ResumeVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    notes: str | None = None
    created_at: datetime


class VersionOutcomeOut(BaseModel):
    """What happened to the applications that used one version. Counts only —
    a response rate over four applications is noise wearing a percent sign."""

    version_id: UUID
    label: str
    applied: int
    responded: int
    statement: str


class ApplicationPatchIn(BaseModel):
    """Fields on an application that are corrections rather than events.

    Notes and which résumé was sent are not things that *happened* on a date,
    so they are edits, not entries in the log.
    """

    notes: str | None = None
    resume_version_id: UUID | None = None
    clear_resume_version: bool = False


# --------------------------------------------------------------------------
# Applications: the board and the funnel
# --------------------------------------------------------------------------


class StageEntryOut(BaseModel):
    """One dated step. The date is the point — a stage without one cannot
    answer how long anything took."""

    event_type: str
    stage: str
    label: str
    occurred_at: datetime
    note: str = ""


class TransitionOut(BaseModel):
    """A stage change that can honestly be logged from where a row is now.

    Served rather than hard-coded in the client so the board and the posting
    window cannot drift into offering different transitions for the same row.
    """

    event_type: str
    label: str
    is_setback: bool = Field(
        default=False, description="Render quieter. A setback is still a fact worth logging."
    )


class ApplicationOut(BaseModel):
    id: UUID
    posting_id: UUID
    posting_title: str
    company_name: str
    posting_url: str
    term_label: str | None = None
    location: str | None = None

    stage: str
    stage_label: str
    is_live: bool
    is_terminal: bool
    timeline: list[StageEntryOut]
    notes: str | None = None
    resume_version_id: UUID | None = None

    days_silent: int | None = Field(
        default=None,
        description="Days since the last employer signal. A subtraction between "
        "two real dates — never a probability of being ghosted.",
    )
    silence_note: str | None = None
    next_events: list[TransitionOut] = []


class TrackedStateOut(BaseModel):
    """Where a posting already sits on the board.

    Discover carries this so a posting that is already applied to can say so
    instead of offering to save it again. It is absent entirely for an untracked
    posting — "not on the board" is not a stage.
    """

    application_id: UUID
    stage: str
    stage_label: str
    is_live: bool
    is_terminal: bool
    applied_at: datetime | None = None
    days_silent: int | None = None
    silence_note: str | None = None
    next_events: list[TransitionOut] = []

    @classmethod
    def from_state(cls, state) -> TrackedStateOut:
        from .applications import STAGE_LABELS, transitions_from

        return cls(
            application_id=state.application_id,
            stage=state.stage.name,
            stage_label=STAGE_LABELS[state.stage],
            is_live=state.stage.is_live,
            is_terminal=state.stage.is_terminal,
            applied_at=state.applied_at,
            days_silent=state.days_silent(),
            silence_note=state.silence_note(),
            next_events=[
                TransitionOut(event_type=t.event_type, label=t.label, is_setback=t.is_setback)
                for t in transitions_from(state.stage)
            ],
        )


class StageCountOut(BaseModel):
    stage: str
    label: str
    reached: int = Field(description="Applications that ever logged this exact stage.")
    current: int = Field(description="Applications sitting here now.")


class ConversionOut(BaseModel):
    from_label: str
    to_label: str
    reached_from: int
    reached_to: int
    has_enough_data: bool
    statement: str = Field(description="Pre-rendered, with both numbers always shown.")


class WaitTimeOut(BaseModel):
    from_label: str
    to_label: str
    sample_size: int
    median_days: int | None
    statement: str


class FunnelOut(BaseModel):
    total: int
    has_enough_data: bool
    basis: str = Field(description="The sample, stated plainly. Render beside the numbers.")
    stages: list[StageCountOut]
    conversions: list[ConversionOut]
    waits: list[WaitTimeOut]


class BoardOut(BaseModel):
    applications: list[ApplicationOut]
    funnel: FunnelOut
    resume_versions: list[ResumeVersionOut] = []
    version_outcomes: list[VersionOutcomeOut] = []


class LogEventIn(BaseModel):
    event_type: str = Field(description="saved | applied | assessment_received | … | accepted")
    occurred_at: datetime | None = Field(
        default=None,
        description="When it actually happened. Defaults to now; pass the real "
        "date when back-filling, because every wait-time figure depends on it.",
    )
    note: str = ""
