"""Request and response shapes for the corpus and onboarding endpoints."""

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
# Stories
# --------------------------------------------------------------------------


class StoryIn(BaseModel):
    """A STAR story. ``source_fact_ids`` is what makes it verifiable — a story
    with none is stored, but flagged, and never used to ground anything."""

    title: str
    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""
    source_fact_ids: list[UUID] = Field(default_factory=list)
    competency_tags: list[str] = Field(default_factory=list)


class StoryOut(StoryIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_grounded: bool = Field(
        description="Backed by at least one real corpus fact. False is a state to fix, "
        "not a failure — it usually means the fact has not been written down yet."
    )
    created_at: datetime
    updated_at: datetime


class CompetencyCoverageOut(BaseModel):
    slug: str
    prompt: str = Field(description="What this competency actually asks for.")
    story_count: int
    story_titles: list[str]


class SourceRelianceOut(BaseModel):
    """One fact carrying an outsized share of the story bank. An interviewer
    hearing four answers about one project notices."""

    fact_id: UUID
    fact_title: str
    story_count: int


class StoryBankOut(BaseModel):
    stories: list[StoryOut]
    story_count: int
    verified_count: int
    note: str
    competencies: list[CompetencyCoverageOut]
    reliance: list[SourceRelianceOut]


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


class StudentProfileIn(BaseModel):
    """The academic half of the profile. Internship counts, not years."""

    school: str | None = None
    major: str | None = None
    degree_level: str | None = Field(
        default=None, description="associate | bachelors | masters | phd"
    )
    graduation_season: str | None = Field(
        default=None, description="spring | summer | fall | winter"
    )
    graduation_year: int | None = Field(default=None, ge=2000, le=2100)
    internships_completed: int = Field(default=0, ge=0, le=20)
    target_role_families: list[str] = Field(
        default_factory=list,
        description="Left empty, these are seeded from the major.",
    )


class StudentProfileOut(StudentProfileIn):
    pass


class MajorOptionsOut(BaseModel):
    """What the profile form offers. Free text is still accepted for major."""

    majors: list[str]
    degree_levels: list[dict[str, str]]


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
    suggested_constraints: ConstraintsOut | None = Field(
        default=None,
        description=(
            "A starting point for an operator who has not set constraints yet, with the "
            "next few applyable cycles preselected. Never a claim about the operator: "
            "`constraints` stays null until they actually answer, which is what "
            "`constraints_set` and the onboarding ladder read."
        ),
    )
    student: StudentProfileOut | None = None
    targets: list[TargetCompanyOut] = Field(default_factory=list)


class CompanySuggestionOut(BaseModel):
    """A company the operator can mark as a target, with how many live postings
    it currently has -- so picking targets is informed rather than blind."""

    name: str
    canonical_name: str
    posting_count: int
    is_target: bool
