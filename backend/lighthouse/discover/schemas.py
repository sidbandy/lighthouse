"""API response shapes for Discover.

Two conventions worth noting, both from the project's operating principles:

* A posting always reports **how** its term was resolved, not a confidence
  score. ``term_rule`` and ``term_evidence`` travel with every row so the UI
  can show "term from title" rather than an opaque number.
* ``description_available`` is exposed deliberately. A match computed from a
  title alone is much weaker evidence than one computed from a full
  description, and the UI has to be able to say so.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..core.models import EmploymentType, RoleFamily, Season, Sponsorship


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


class PostingDetail(PostingSummary):
    description: str | None = None
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
