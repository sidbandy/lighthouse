"""Response shapes for Discover.

Postings carry ``term_rule`` and ``term_evidence`` so the UI can say how a cycle
was resolved, and ``description_available`` so it can say how much a match score
is worth.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..core.models import EmploymentType, RoleFamily, Season, Sponsorship
from ..track.schemas import TrackedStateOut


class SourceSighting(BaseModel):
    """Where a posting was seen. Provenance is first-class: the operator should
    be able to tell a role listed on six lists from one seen once."""

    model_config = ConfigDict(from_attributes=True)

    source_id: str
    source_url: str
    seen_at: datetime


class PostingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_name: str
    title: str
    url: str

    season: Season | None = None
    term_year: int | None = None
    term_label: str | None = Field(
        default=None, description="Human label, e.g. 'Summer 2027'. None when unresolved."
    )
    term_rule: str = Field(description="Which rule resolved the term, or 'unknown'.")
    term_evidence: str | None = Field(
        default=None, description="The text that triggered the rule, for the operator to check."
    )

    employment_type: EmploymentType
    role_family: RoleFamily
    sponsorship: Sponsorship

    location_labels: list[str] = []
    is_remote: bool = False
    is_active: bool = True
    description_available: bool = False

    posted_at: datetime | None = None
    age_days: int | None = Field(
        default=None, description="Days since posted. Drives ghost-job signals."
    )

    source_ids: list[str] = Field(
        default=[], description="Every feed this posting was seen on, deduplicated."
    )
    source_count: int = 0

    tracked: TrackedStateOut | None = Field(
        default=None,
        description="Where this posting already sits on the board, or None if untracked. "
        "On a list of thousands, 'have I applied to this?' is the one question the tool "
        "should never make you answer from memory.",
    )


class GhostSignalOut(BaseModel):
    """One checked fact, with the observation that produced it."""

    name: str
    verdict: str
    detail: str


class GhostAssessmentOut(BaseModel):
    """A checklist, never a score. The label is derived from the signals and
    always travels with them so the operator can judge for themselves."""

    label: str
    summary: str
    signals: list[GhostSignalOut]


class TermMatchOut(BaseModel):
    """One posting term and how the corpus relates to it. Every field is a
    fact the operator can check against the posting, not a derived score."""

    term: str
    posting_count: int
    corpus_count: int
    is_technical: bool
    emphasis: str = Field(description="'core' (>=5x), 'important' (>=3x), or 'mentioned'.")
    component_evidence: list[str] = Field(
        default=[], description="For a reword: the corpus words that already cover this phrase."
    )


class MatchOut(BaseModel):
    """The three-bucket keyword breakdown. The score is secondary to these
    lists, which are what the operator can actually act on."""

    score: int
    evidence_basis: str = Field(description="How much the score is worth, in plain words.")
    thin_evidence: bool
    summary: str
    corpus_size: int = Field(
        default=0,
        description="Facts in the corpus at scoring time. Zero means the score is an absence "
        "of data rather than a judgement, and the UI must say so rather than render a 0.",
    )
    matched: list[TermMatchOut] = []
    reword: list[TermMatchOut] = Field(
        default=[], description="Experience the corpus has under different wording."
    )
    gaps: list[TermMatchOut] = Field(
        default=[], description="Emphasised terms with no corpus support. Real gaps, not keywords."
    )


class LaneOut(BaseModel):
    lane: str
    selectivity: int
    reason: str


class ScoredPostingOut(PostingSummary):
    match: MatchOut
    lane: LaneOut


class LaneBucketOut(BaseModel):
    """One lane of the three-lane view, with its suggested weekly quota."""

    lane: str
    weekly_quota: int
    count: int = Field(description="How many are being returned.")
    scored_in_lane: int = Field(
        default=0, description="How many this lane holds in the slice that was scored."
    )
    has_more: bool = Field(
        default=False,
        description="The lane is holding more than it is showing. Without this the list "
        "just stops, and a cap is indistinguishable from the end of the market.",
    )
    postings: list[ScoredPostingOut]


class BriefFactOut(BaseModel):
    """One fact lifted out of the description, with the sentence it came from.

    ``evidence`` always travels with ``value``: a regex over free prose is wrong
    often enough that a figure the operator cannot check is worse than none.
    """

    kind: str
    label: str
    value: str
    evidence: str


class PostingBriefOut(BaseModel):
    """The decision-relevant contents of a description, pulled to the top.

    Every field is extracted, never inferred. A posting that does not state its
    pay has no ``compensation`` — it is not estimated from the title or the
    market.
    """

    logistics: list[BriefFactOut] = Field(
        default_factory=list, description="Pay, working pattern, length, deadline, GPA."
    )
    process: list[BriefFactOut] = Field(
        default_factory=list, description="Interview stages the posting names outright."
    )
    responsibilities: list[str] = Field(default_factory=list)
    is_thin: bool = Field(
        default=False,
        description="The description named nothing concrete. That absence is itself a signal.",
    )


class EligibilityOut(BaseModel):
    """Whether the operator's graduation term clears this posting's window.

    ``not_stated`` is the honest and most common answer: most postings say
    nothing, and that must never be reported as a pass or a fail.
    """

    verdict: str = Field(description="eligible | not_eligible | not_stated")
    headline: str
    detail: str
    evidence: str | None = None
    is_blocking: bool = False


class PostingDetail(PostingSummary):
    description: str | None = None
    brief: PostingBriefOut | None = None
    eligibility: EligibilityOut | None = None
    match: MatchOut | None = None
    ghost: GhostAssessmentOut | None = None
    ats_vendor: str | None = None
    ats_job_id: str | None = None
    sources: list[SourceSighting] = []
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class PostingPage(BaseModel):
    """A page of results plus the totals needed to render filter counts."""

    items: list[PostingSummary]
    total: int
    limit: int
    offset: int


class CycleCount(BaseModel):
    term_label: str
    season: Season
    term_year: int
    count: int


class SourceHealthOut(BaseModel):
    """Sources rot. This is what makes that visible rather than silent."""

    model_config = ConfigDict(from_attributes=True)

    source_id: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_row_count: int | None = None
    previous_row_count: int | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    is_quarantined: bool = False


class IngestSourceResult(BaseModel):
    source_id: str
    ok: bool
    row_count: int = 0
    error: str | None = None
    quarantined: bool = False


class IngestResultOut(BaseModel):
    summary: str
    raw_count: int
    merged_count: int
    created: int
    updated: int
    skipped_not_applyable: int
    term_rules: dict[str, int]
    sources: list[IngestSourceResult]
