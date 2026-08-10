"""SQLAlchemy models.

Two families of tables, and the split matters (plan §6):

* **Shared** tables describe the world — companies, postings, source health.
  They have no ``user_id`` because they are identical for every operator.
* **Personal** tables describe one operator — corpus, events, applications.
  They all carry ``user_id``, defaulted to the singleton operator today, so
  that multi-user later is a config change rather than a schema migration.

Everything that changes state also appends to :class:`Event`; the event log is
append-only and is what makes funnel analytics and "what happened when"
possible. Nothing overwrites history.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import DEFAULT_OPERATOR_ID

EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _operator_fk() -> Mapped[uuid.UUID]:
    """Personal-table scoping column. See module docstring."""
    return mapped_column(
        PgUUID(as_uuid=True), nullable=False, default=DEFAULT_OPERATOR_ID, index=True
    )


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Season(enum.StrEnum):
    """The four recruiting cycles. Genuinely fixed, so a native enum is safe."""

    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"
    WINTER = "winter"


class Sponsorship(enum.StrEnum):
    UNKNOWN = "unknown"
    OFFERS = "offers"
    DOES_NOT_OFFER = "does_not_offer"
    CITIZENSHIP_REQUIRED = "citizenship_required"


class RoleFamily(enum.StrEnum):
    """Role families across the majors Lighthouse serves -- not just CS. Stored
    as a plain string column (see ``Posting.role_family``) so this taxonomy can
    grow without an enum migration each time."""

    SWE = "swe"
    AI_ML = "ai_ml"
    DATA = "data"
    HARDWARE = "hardware"
    QUANT = "quant"
    SECURITY = "security"
    PRODUCT = "product"
    DESIGN = "design"
    FINANCE = "finance"
    CONSULTING = "consulting"
    BUSINESS = "business"
    MARKETING = "marketing"
    MECHANICAL = "mechanical"
    SCIENCE = "science"
    OTHER = "other"


class EmploymentType(enum.StrEnum):
    INTERNSHIP = "internship"
    NEW_GRAD = "new_grad"
    OTHER = "other"


# ``term_rule`` and ``fact_type`` are stored as plain strings rather than native
# enums: both are expected to gain members (new resolution rules, new fact
# kinds), and a string column avoids an ALTER TYPE migration each time.

# Which rule in the cascade resolved a posting's term. Stored as evidence the
# UI can show ("term from title") instead of an opaque confidence number.
TERM_RULE_EXPLICIT_FIELD = "explicit_field"  # source already gave us the term
TERM_RULE_TITLE = "title_token"
TERM_RULE_DESCRIPTION_DATES = "description_dates"
TERM_RULE_ELIGIBILITY = "eligibility_phrase"
TERM_RULE_COMPANY_HISTORY = "company_history"
TERM_RULE_UNKNOWN = "unknown"


# --------------------------------------------------------------------------
# Shared: companies and postings
# --------------------------------------------------------------------------


class Company(Base):
    """One real-world company.

    ``canonical_name`` is the normalized key used for dedup blocking; ``name``
    is what we show. Entity resolution across "Meta"/"Facebook"/"Meta Platforms
    Inc." is deliberately conservative — we would rather keep two rows than
    merge two genuinely different companies.
    """

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)

    # ATS slug map, seeded from public data. Powers direct-ATS polling and the
    # careers-page check used by ghost-job signals.
    ats_vendor: Mapped[str | None] = mapped_column(String(40))
    ats_slug: Mapped[str | None] = mapped_column(Text)
    careers_url: Mapped[str | None] = mapped_column(Text)

    # Operator-maintained selectivity tier used by the three-lane view. A small
    # config table, not a machine learning problem. Strictly *how hard is this
    # company to get into*, which is true of the company regardless of who is
    # looking — "I want to work here" is personal and lives in
    # :class:`OperatorTarget`. Conflating the two once demoted every company the
    # operator marked, so wanting Jane Street moved it out of Reach.
    tier: Mapped[str | None] = mapped_column(String(40))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    postings: Mapped[list[Posting]] = relationship(back_populates="company")

    __table_args__ = (Index("ix_companies_ats", "ats_vendor", "ats_slug"),)


class Posting(Base):
    """A canonical, deduplicated job posting.

    One row per real-world opening. The same Optiver role appearing on Simplify,
    vansh and Indeed collapses into a single ``Posting`` with three
    :class:`PostingSource` rows, which is what lets the UI say "seen on 3 lists".
    """

    __tablename__ = "postings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # Identity-bearing ATS job id (e.g. Greenhouse gh_jid). When two candidate
    # rows disagree here they are different roles, full stop -- this is an
    # absolute veto on merging, not a weighted signal.
    ats_job_id: Mapped[str | None] = mapped_column(String(120), index=True)

    description: Mapped[str | None] = mapped_column(Text)
    # Many GitHub-sourced rows are title-only. A high match score computed from
    # a title alone is much weaker evidence, and the UI must say so.
    description_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Cycle. ``term_rule`` records *which* rule resolved it; unresolved rows
    # keep NULL season/year and are filterable rather than guessed.
    season: Mapped[Season | None] = mapped_column(Enum(Season, name="season"))
    term_year: Mapped[int | None] = mapped_column(Integer)
    term_rule: Mapped[str] = mapped_column(String(40), default=TERM_RULE_UNKNOWN, nullable=False)
    term_evidence: Mapped[str | None] = mapped_column(Text)

    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType, name="employment_type"), default=EmploymentType.INTERNSHIP
    )
    # Plain string, not a native enum: the role taxonomy grows as Lighthouse
    # covers more majors, and a string column avoids an ALTER TYPE each time.
    # Values still come from RoleFamily.
    role_family: Mapped[str] = mapped_column(
        String(20), default=RoleFamily.OTHER.value, nullable=False, index=True
    )
    sponsorship: Mapped[Sponsorship] = mapped_column(
        Enum(Sponsorship, name="sponsorship"), default=Sponsorship.UNKNOWN
    )

    # Superset of every location seen across sources: [{city, state, raw}].
    locations: Mapped[list] = mapped_column(JSONB, default=list)
    location_labels: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship(back_populates="postings")
    sources: Mapped[list[PostingSource]] = relationship(
        back_populates="posting", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_postings_term", "season", "term_year"),
        Index("ix_postings_active_posted", "is_active", "posted_at"),
    )


class PostingSource(Base):
    """Provenance: one row per (posting, source) sighting.

    ``source_fingerprint`` is a hash of the raw upstream row, which makes
    re-ingesting the same unchanged row a no-op and lets us diff runs to find
    genuinely new postings.
    """

    __tablename__ = "posting_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    posting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("postings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    posting: Mapped[Posting] = relationship(back_populates="sources")

    __table_args__ = (
        UniqueConstraint("source_id", "source_fingerprint", name="uq_source_fingerprint"),
    )


class SourceHealth(Base):
    """Per-source liveness. Sources rot; Lighthouse says so rather than
    silently shrinking the list.

    A run that returns fewer than half the previous run's rows is treated as a
    parse failure: prior data is kept and an alert is raised.
    """

    __tablename__ = "source_health"

    source_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_row_count: Mapped[int | None] = mapped_column(Integer)
    previous_row_count: Mapped[int | None] = mapped_column(Integer)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    is_quarantined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# --------------------------------------------------------------------------
# Personal: the corpus
# --------------------------------------------------------------------------


class OperatorProfile(Base):
    """What the operator is looking for: one row per operator.

    Onboarding collects this (locations, sponsorship stance, target cycles) and
    Discover reads it to seed filters. It is a singleton keyed by ``user_id``
    rather than a settings blob so the columns stay typed and queryable, and so
    the multi-user split described in the module docstring keeps working.

    Everything is nullable-with-a-default: a half-finished profile is a normal
    state during onboarding, not an error.
    """

    __tablename__ = "operator_profiles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, default=DEFAULT_OPERATOR_ID, unique=True, index=True
    )

    preferred_locations: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    open_to_remote: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sponsorship: Mapped[str] = mapped_column(String(30), default="us_authorized", nullable=False)
    weekly_study_hours: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    target_cycles: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    # --- Who the operator is academically -------------------------------
    # Lighthouse is for students and new grads, so the profile is described in
    # the terms a student has: a major, a graduation term, and a count of
    # internships. Deliberately NOT "years of experience" -- a sophomore has
    # none, and asking makes the tool feel written for somebody else.
    school: Mapped[str | None] = mapped_column(Text)
    # Free text, because "Mechanical Engineering & Economics" is a real answer
    # and an enum of majors would be wrong within a week.
    major: Mapped[str | None] = mapped_column(Text)
    degree_level: Mapped[str | None] = mapped_column(String(20))

    # The single most useful eligibility fact there is. Most internships state a
    # graduation window, and applying outside it is the commonest wasted
    # application a student makes -- so this is stored as season + year and
    # checked against what the posting says.
    graduation_season: Mapped[Season | None] = mapped_column(
        Enum(Season, name="season"), nullable=True
    )
    graduation_year: Mapped[int | None] = mapped_column(Integer)

    # Counts, not years.
    internships_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Role families this operator is actually looking for, seeded from their
    # major and then editable. Drives the default Discover filter.
    target_role_families: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OperatorTarget(Base):
    """A company this operator wants to work at.

    Personal, so it carries ``user_id`` and does not live as a flag on the
    shared :class:`Company` row — one operator's ambitions are not a property of
    the company, and writing them there would make every operator share them.
    """

    __tablename__ = "operator_targets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _operator_fk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_operator_targets_user_company"),
    )


class CorpusFact(Base):
    """One real thing the operator did: a project, job, skill, achievement.

    This is the spine. Match scoring, stories, resume tailoring and mock
    feedback all read from here, which is what stops the resume, the STAR
    answers and the outreach from telling three different versions of the same
    story.
    """

    __tablename__ = "corpus_facts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _operator_fk()

    fact_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    # Tech stack, dates, metrics, links.
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "fact_type IN ('project','experience','skill','achievement','education')",
            name="ck_fact_type",
        ),
    )


class CorpusStory(Base):
    """A STAR behavioral answer, grounded in :class:`CorpusFact` rows.

    ``source_fact_ids`` is how zero-fabrication is enforced: a story with an
    empty list is flagged unverified in the UI and excluded from mock-interview
    grounding, because we will not coach the operator to repeat something that
    does not trace back to a real fact.
    """

    __tablename__ = "corpus_stories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _operator_fk()

    title: Mapped[str] = mapped_column(Text, nullable=False)
    situation: Mapped[str] = mapped_column(Text, default="")
    task: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")

    source_fact_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PgUUID(as_uuid=True)), default=list
    )
    competency_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def is_grounded(self) -> bool:
        return bool(self.source_fact_ids)


# --------------------------------------------------------------------------
# Personal: the event log
# --------------------------------------------------------------------------


class Event(Base):
    """Append-only state change.

    ``occurred_at`` is when the thing actually happened; ``recorded_at`` is when
    the operator got round to logging it. They routinely differ by days.
    Analytics use ``occurred_at``; freshness checks use ``recorded_at``.
    """

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _operator_fk()

    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_events_entity", "entity_type", "entity_id", "occurred_at"),)


# --------------------------------------------------------------------------
# Personal: applications and resumes
# --------------------------------------------------------------------------


class Application(Base):
    """The operator's application to a posting.

    Deliberately has no mutable ``status`` column: state is derived by folding
    the :class:`Event` log, so history is never overwritten.
    """

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _operator_fk()

    posting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("postings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "posting_id", name="uq_application_posting"),)


class ResumeVersion(Base):
    """A resume PDF the operator wrote. Lighthouse tracks and scores; it does
    not generate. No lineage graph, no bullet-level genealogy -- just which
    version went where."""

    __tablename__ = "resume_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _operator_fk()

    label: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------------------
# Personal: networking
# --------------------------------------------------------------------------


class Contact(Base):
    """Someone the operator knows, or wants to.

    Names arrive by paste, from LinkedIn's own Alumni tool -- a first-party
    feature built for exactly this. Nothing is scraped, which is a boundary in
    code and not a preference: the operator's own account is needed for the
    search, and losing it would cost more than the automation saves.

    ``school`` is stored per contact rather than inferred, because "we went to
    the same place" is the one edge a student reliably has, and it has to be a
    fact they entered rather than a guess.
    """

    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _operator_fk()

    name: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    # Kept even when company_id resolves, because the operator pasted it and it
    # is what they will recognise if entity resolution ever gets it wrong.
    company_name: Mapped[str | None] = mapped_column(Text)
    role_title: Mapped[str | None] = mapped_column(Text)

    relationship_type: Mapped[str] = mapped_column(String(30), default="cold", nullable=False)
    school: Mapped[str | None] = mapped_column(Text)
    grad_year: Mapped[int | None] = mapped_column(Integer)
    # 1-5, the operator's own read of how well they know this person. Their
    # judgement, never computed -- a "relationship strength" derived from
    # message counts would be exactly the invented number this project refuses.
    strength: Mapped[int | None] = mapped_column(Integer)

    email: Mapped[str | None] = mapped_column(Text)
    profile_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    interactions: Mapped[list[ContactInteraction]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('cold','warm_intro','alumni','met_at_event','referred_by')",
            name="ck_contact_relationship",
        ),
        CheckConstraint(
            "strength IS NULL OR (strength >= 1 AND strength <= 5)",
            name="ck_contact_strength",
        ),
        Index("ix_contacts_user_company", "user_id", "company_id"),
    )


class ContactInteraction(Base):
    """One dated exchange with a contact.

    This is the append-only log for networking, the same shape the application
    board uses -- state is folded from it rather than stored, so the follow-up
    engine works from real dates and a correction adds a row instead of
    overwriting one.

    It carries ``summary`` because an interaction has content that a bare state
    change does not, and that content is the whole difference between a
    follow-up that gets answered and "just checking in!". A message three weeks
    after a coffee chat should reference what was actually discussed.
    """

    __tablename__ = "contact_interactions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _operator_fk()
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Set when this exchange was about a specific application -- a referral ask,
    # or a thank-you after an interview. It is what lets the funnel separate
    # referred applications from cold ones.
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), index=True
    )

    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10), default="outbound", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    contact: Mapped[Contact] = relationship(back_populates="interactions")

    __table_args__ = (
        CheckConstraint("direction IN ('outbound','inbound')", name="ck_interaction_direction"),
        Index("ix_interactions_contact_time", "contact_id", "occurred_at"),
    )


# --------------------------------------------------------------------------
# Shared: company interview intelligence (populated from Phase 3 onward)
# --------------------------------------------------------------------------


class ReportedQuestion(Base):
    """A question someone publicly reported being asked.

    Individual problems get retired but *patterns* persist, so the useful
    aggregate is over ``pattern_tags``, weighted by how recent the report is.
    """

    __tablename__ = "reported_questions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    problem_slug: Mapped[str | None] = mapped_column(Text)
    pattern_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    stage: Mapped[str | None] = mapped_column(String(30))
    reported_date: Mapped[date | None] = mapped_column(Date, index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)


class PracticeAttempt(Base):
    """One attempt at one problem. The raw material for the per-pattern record
    that drives study prioritisation -- stored as outcomes, never collapsed
    into a mastery score."""

    __tablename__ = "practice_attempts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _operator_fk()

    problem_slug: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    time_taken_sec: Mapped[int | None] = mapped_column(Integer)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('solved_clean','solved_with_hint','solved_over_time','failed')",
            name="ck_attempt_outcome",
        ),
    )
