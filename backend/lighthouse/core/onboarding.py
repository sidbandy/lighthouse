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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .corpus import CorpusSummary, FactInput, add_fact, summarize
from .models import Company, OperatorProfile, OperatorTarget
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


def default_constraints() -> OperatorConstraints:
    """A sensible starting point: the next few applyable cycles preselected."""
    from datetime import date

    from ..ingest.seasons import applyable_cycles

    return OperatorConstraints(target_cycles=[c.label for c in applyable_cycles(date.today())[:3]])
