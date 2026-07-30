"""API shapes for the Track module: ATS check and per-posting tailoring."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
