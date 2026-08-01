"""API response shapes for the corpus and onboarding.

The conventions here follow the project's operating principles:

* **Drafts are never facts.** Resume extraction returns
  :class:`DraftFactOut` objects that carry no id, because nothing has been
  saved. They become facts only when the operator confirms them, which is what
  keeps the corpus free of anything a human has not vouched for.
* **Counts, with their sample.** Every figure in :class:`CoverageOut` is an
  observed count, and the sample it was drawn from travels alongside it.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


class FactIn(BaseModel):
    """A fact the operator is creating or editing."""

    fact_type: str = Field(description="project | experience | skill | achievement | education")
    title: str
    body: str = ""
    metadata: dict = Field(default_factory=dict)


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fact_type: str
    title: str
    body: str = ""
    metadata: dict = Field(default_factory=dict, validation_alias="meta")
    created_at: datetime
    updated_at: datetime


class DraftFactOut(BaseModel):
    """An extracted candidate fact. Deliberately has no id: it is not saved,
    and the operator may edit or discard it before it ever becomes one."""

    fact_type: str
    title: str
    body: str = ""


class ExtractionOut(BaseModel):
    """The result of reading a resume PDF. Nothing here has been persisted."""

    drafts: list[DraftFactOut]
    page_count: int
    char_count: int
    likely_image_based: bool = Field(
        description="Almost no text came out, which usually means a scanned image. "
        "An ATS would get nothing from it either."
    )
    note: str


class CorpusSummaryOut(BaseModel):
    fact_count: int
    facts_by_type: dict[str, int]
    story_count: int
    unverified_story_count: int
    is_usable_for_matching: bool
    readiness_note: str


class CorpusOut(BaseModel):
    facts: list[FactOut]
    summary: CorpusSummaryOut


# --------------------------------------------------------------------------
# Corpus coverage against the live market
# --------------------------------------------------------------------------


class TermDemandOut(BaseModel):
    term: str
    posting_count: int = Field(description="Sampled postings mentioning this term.")
    core_count: int = Field(description="Sampled postings repeating it enough to read as central.")
    is_technical: bool


class FactContributionOut(BaseModel):
    fact_id: UUID
    fact_type: str
    title: str
    terms: list[TermDemandOut]
    reach: int = Field(description="Sampled postings mentioning at least one of this fact's terms.")
    unique_reach: int = Field(description="Of those, the ones no other fact reaches.")
    unmatched_term_count: int


class CoverageOut(BaseModel):
    sample_size: int
    is_meaningful: bool
    basis: str = Field(description="The sample, stated plainly. Show this next to the numbers.")
    fact_count: int
    reached: int
    unreached: int
    contributions: list[FactContributionOut]
    gaps: list[TermDemandOut]


# --------------------------------------------------------------------------
# Onboarding
# --------------------------------------------------------------------------


class ConstraintsIn(BaseModel):
    preferred_locations: list[str] = Field(default_factory=list)
    open_to_remote: bool = True
    sponsorship: str = "us_authorized"
    weekly_study_hours: int = Field(default=10, ge=0, le=168)
    target_cycles: list[str] = Field(default_factory=list)


class ConstraintsOut(ConstraintsIn):
    pass


class TargetCompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    canonical_name: str
    tier: str | None = None
    selectivity: int = Field(description="1-4, higher is more selective. Never set by wanting it.")


class OnboardingOut(BaseModel):
    next_step: str = Field(
        description="upload_resume | add_projects | pick_targets | set_constraints | complete"
    )
    is_complete: bool
    corpus: CorpusSummaryOut
    target_company_count: int
    constraints_set: bool
    constraints: ConstraintsOut | None = None
    targets: list[TargetCompanyOut] = Field(default_factory=list)


class CompanySuggestionOut(BaseModel):
    """A company the operator can mark as a target, with how many live postings
    it currently has -- so picking targets is informed rather than blind."""

    name: str
    canonical_name: str
    posting_count: int
    is_target: bool
