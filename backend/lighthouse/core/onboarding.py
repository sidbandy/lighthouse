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

from dataclasses import asdict, dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .corpus import CorpusSummary, FactInput, add_fact, summarize
from .models import Company
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


def set_target_companies(session: Session, names: list[str]) -> int:
    """Mark companies as targets.

    Reuses existing company rows where the name already appears in the ingested
    data, and creates a lightweight row otherwise, so a target the lists have
    not surfaced yet is still tracked.
    """
    from ..ingest.normalize import canonical_company

    marked = 0
    for name in names:
        canonical = canonical_company(name)
        if not canonical:
            continue
        company = session.scalar(select(Company).where(Company.canonical_name == canonical))
        if company is None:
            company = Company(name=name.strip(), canonical_name=canonical)
            session.add(company)
        if company.tier is None:
            company.tier = "target"
        marked += 1
    session.flush()
    return marked


def target_company_count(session: Session) -> int:
    return int(session.scalar(select(func.count(Company.id)).where(Company.tier.isnot(None))) or 0)


def onboarding_state(
    session: Session, *, constraints: OperatorConstraints | None = None
) -> OnboardingState:
    return OnboardingState(
        corpus=summarize(session),
        target_company_count=target_company_count(session),
        constraints_set=constraints is not None and bool(constraints.preferred_locations),
    )


def constraints_to_dict(constraints: OperatorConstraints) -> dict:
    return asdict(constraints)


def default_constraints() -> OperatorConstraints:
    """A sensible starting point: the next few applyable cycles preselected."""
    from datetime import date

    from ..ingest.seasons import applyable_cycles

    return OperatorConstraints(target_cycles=[c.label for c in applyable_cycles(date.today())[:3]])
