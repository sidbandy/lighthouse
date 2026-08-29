"""Onboarding: from empty to usefully personalised in one sitting.

Match scoring is meaningless against an empty corpus, so the first run has to
reach a usable baseline quickly. The steps, in order of payoff:

1. Extract a resume into draft facts (operator reviews and corrects).
2. Add a few real projects with detail.
3. Pick target companies, which seeds the three-lane view and Tier-3 polling.
4. Set constraints -- location, sponsorship need, study hours.

After step 2 match scoring already works; the rest sharpens it. Nothing here
commits anything the operator has not seen: drafts are returned for review, not
written silently, because the corpus must contain only real facts.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .corpus import CorpusSummary, FactInput, add_fact, summarize
from .majors import DEGREE_LEVELS
from .models import Company, OperatorProfile, OperatorTarget, Season
from .resume import ExtractedResume, extract_pdf

# Sponsorship stance drives a top-level filter, so it is asked up front.
SPONSORSHIP_CHOICES = ("needs_sponsorship", "us_authorized", "us_citizen")


@dataclass(slots=True)
class OperatorConstraints:
    """What the operator is looking for, used to seed filters and planning."""

    preferred_locations: list[str] = field(default_factory=list)
    open_to_remote: bool = True
    sponsorship: str = "us_authorized"
    weekly_study_hours: int = 10
    target_cycles: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StudentProfile:
    """Who the operator is academically. Counts of internships, not years of
    experience -- a sophomore has none of the latter."""

    school: str | None = None
    major: str | None = None
    degree_level: str | None = None
    graduation_season: str | None = None
    graduation_year: int | None = None
    internships_completed: int = 0
    target_role_families: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OnboardingState:
    """Where the operator is in setup, and what to do next."""

    corpus: CorpusSummary
    target_company_count: int
    constraints_set: bool

    @property
    def next_step(self) -> str:
        if self.corpus.fact_count == 0:
            return "upload_resume"
        if not self.corpus.is_usable_for_matching:
            return "add_projects"
        if self.target_company_count == 0:
            return "pick_targets"
        if not self.constraints_set:
            return "set_constraints"
        return "complete"

    @property
    def is_complete(self) -> bool:
        return self.next_step == "complete"


def draft_facts_from_resume(path: str) -> ExtractedResume:
    """Parse a resume into draft facts for review. Nothing is saved here."""
    return extract_pdf(path)


def commit_reviewed_facts(session: Session, facts: list[FactInput]) -> list:
    """Persist the facts the operator confirmed.

    Called after review, never straight from extraction, so the corpus only
    ever contains facts a human has actually vouched for.
    """
    return [add_fact(session, fact.validated()) for fact in facts]


def set_target_companies(
    session: Session,
    names: list[str],
    *,
    replace: bool = True,
    user_id: uuid.UUID | None = None,
) -> int:
    """Mark companies as targets for this operator.

    Reuses existing company rows where the name already appears in the ingested
    data, and creates a lightweight row otherwise, so a target the lists have
    not surfaced yet is still tracked.

    Note what this deliberately does *not* touch: ``Company.tier``. Selectivity
    is how hard a company is to get into, and wanting to work somewhere does not
    make it easier. Writing both to one column previously demoted every marked
    company to mid selectivity, which moved elite firms out of the Reach lane.
    """
    from ..ingest.normalize import canonical_company

    uid = user_id or _operator_id()

    if replace:
        for existing in session.scalars(
            select(OperatorTarget).where(OperatorTarget.user_id == uid)
        ):
            session.delete(existing)
        session.flush()

    marked = 0
    for name in names:
        canonical = canonical_company(name)
        if not canonical:
            continue
        company = session.scalar(select(Company).where(Company.canonical_name == canonical))
        if company is None:
            company = Company(name=name.strip(), canonical_name=canonical)
            session.add(company)
            session.flush()
        already = session.scalar(
            select(OperatorTarget).where(
                OperatorTarget.user_id == uid, OperatorTarget.company_id == company.id
            )
        )
        if already is None:
            session.add(OperatorTarget(user_id=uid, company_id=company.id))
        marked += 1
    session.flush()
    return marked


def target_companies(session: Session, *, user_id: uuid.UUID | None = None) -> list[Company]:
    return list(
        session.scalars(
            select(Company)
            .join(OperatorTarget, OperatorTarget.company_id == Company.id)
            .where(OperatorTarget.user_id == (user_id or _operator_id()))
            .order_by(Company.name)
        )
    )


def target_company_count(session: Session, *, user_id: uuid.UUID | None = None) -> int:
    return int(
        session.scalar(
            select(func.count(OperatorTarget.id)).where(
                OperatorTarget.user_id == (user_id or _operator_id())
            )
        )
        or 0
    )


def _operator_id() -> uuid.UUID:
    return get_settings().operator_id


def load_profile(session: Session, *, user_id: uuid.UUID | None = None) -> OperatorProfile | None:
    """The operator's profile row, or ``None`` if they have not started one."""
    return session.scalar(
        select(OperatorProfile).where(OperatorProfile.user_id == (user_id or _operator_id()))
    )


def load_constraints(
    session: Session, *, user_id: uuid.UUID | None = None
) -> OperatorConstraints | None:
    """The operator's saved constraints, or ``None`` if they never set any.

    ``None`` and "saved but empty" are genuinely different states -- the first
    means onboarding still has a step to go, the second means the operator
    looked at the question and answered it -- so the absence is preserved rather
    than being papered over with defaults.
    """
    profile = session.scalar(
        select(OperatorProfile).where(OperatorProfile.user_id == (user_id or _operator_id()))
    )
    if profile is None:
        return None
    return OperatorConstraints(
        preferred_locations=list(profile.preferred_locations or []),
        open_to_remote=profile.open_to_remote,
        sponsorship=profile.sponsorship,
        weekly_study_hours=profile.weekly_study_hours,
        target_cycles=list(profile.target_cycles or []),
    )


def load_student_profile(
    session: Session, *, user_id: uuid.UUID | None = None
) -> StudentProfile | None:
    profile = load_profile(session, user_id=user_id)
    if profile is None:
        return None
    return StudentProfile(
        school=profile.school,
        major=profile.major,
        degree_level=profile.degree_level,
        graduation_season=profile.graduation_season.value if profile.graduation_season else None,
        graduation_year=profile.graduation_year,
        internships_completed=profile.internships_completed,
        target_role_families=list(profile.target_role_families or []),
    )


def save_student_profile(
    session: Session, data: StudentProfile, *, user_id: uuid.UUID | None = None
) -> OperatorProfile:
    """Upsert the academic half of the profile.

    Role families are seeded from the major on first save so a student is not
    asked to pick out of a taxonomy they have never seen; once set, whatever
    they chose is kept.
    """
    from .majors import role_families_for

    if data.degree_level and data.degree_level not in {level for level, _ in DEGREE_LEVELS}:
        raise ValueError(f"unknown degree_level {data.degree_level!r}")
    if data.graduation_year is not None and not (2000 <= data.graduation_year <= 2100):
        raise ValueError("graduation_year is outside a plausible range")
    if data.internships_completed < 0:
        raise ValueError("internships_completed cannot be negative")
    season = None
    if data.graduation_season:
        try:
            season = Season(data.graduation_season.lower())
        except ValueError as exc:
            raise ValueError(f"unknown graduation_season {data.graduation_season!r}") from exc

    uid = user_id or _operator_id()
    profile = session.scalar(select(OperatorProfile).where(OperatorProfile.user_id == uid))
    if profile is None:
        profile = OperatorProfile(user_id=uid)
        session.add(profile)

    profile.school = (data.school or "").strip() or None
    profile.major = (data.major or "").strip() or None
    profile.degree_level = data.degree_level
    profile.graduation_season = season
    profile.graduation_year = data.graduation_year
    profile.internships_completed = data.internships_completed

    families = [f.strip() for f in data.target_role_families if f.strip()]
    profile.target_role_families = families or role_families_for(profile.major)
    session.flush()
    return profile


def save_constraints(
    session: Session, constraints: OperatorConstraints, *, user_id: uuid.UUID | None = None
) -> OperatorProfile:
    """Upsert the operator's constraints. One row per operator, by design."""
    if constraints.sponsorship not in SPONSORSHIP_CHOICES:
        raise ValueError(
            f"sponsorship must be one of {list(SPONSORSHIP_CHOICES)}, "
            f"got {constraints.sponsorship!r}"
        )
    if constraints.weekly_study_hours < 0:
        raise ValueError("weekly_study_hours cannot be negative")

    uid = user_id or _operator_id()
    profile = session.scalar(select(OperatorProfile).where(OperatorProfile.user_id == uid))
    if profile is None:
        profile = OperatorProfile(user_id=uid)
        session.add(profile)

    profile.preferred_locations = [
        loc.strip() for loc in constraints.preferred_locations if loc.strip()
    ]
    profile.open_to_remote = constraints.open_to_remote
    profile.sponsorship = constraints.sponsorship
    profile.weekly_study_hours = constraints.weekly_study_hours
    profile.target_cycles = [c.strip() for c in constraints.target_cycles if c.strip()]
    session.flush()
    return profile


def onboarding_state(
    session: Session, *, constraints: OperatorConstraints | None = None
) -> OnboardingState:
    """Where setup stands. Constraints are read from storage unless supplied."""
    if constraints is None:
        constraints = load_constraints(session)
    return OnboardingState(
        corpus=summarize(session),
        target_company_count=target_company_count(session),
        constraints_set=constraints is not None,
    )


def constraints_to_dict(constraints: OperatorConstraints) -> dict:
    return asdict(constraints)


def default_constraints(today: date | None = None) -> OperatorConstraints:
    """A starting point: the cycles open right now, plus the next Summer.

    Summer is named rather than taken from the front of the list, because the
    front of the list is not where it is. From August 2026 the soonest three
    applyable cycles are Fall 2026, Winter 2027 and Spring 2027 -- and Winter
    and Spring carry 32 and 29 live postings against Summer 2027's 294. Summer
    is the main internship cycle; the off-cycles are the small ones that happen
    to start sooner. Slicing the first three drops exactly the cycle the
    operator is most likely recruiting for, which is a bad thing for a default
    to do quietly.

    This is a suggestion, never an answer. It seeds the form; storage stays
    empty until the operator saves, which is what the onboarding ladder reads.
    """
    from ..core.models import Season
    from ..ingest.seasons import applyable_cycles

    cycles = applyable_cycles(today or date.today())
    chosen = cycles[:3]
    summer = next((c for c in cycles if c.season is Season.SUMMER), None)
    if summer is not None and summer not in chosen:
        chosen = sorted([*chosen, summer], key=lambda c: c.sort_key)
    return OperatorConstraints(target_cycles=[c.label for c in chosen])
