"""The corpus service: the operator's own facts and stories.

This is the spine of the whole tool. Match scoring, the keyword tailor, stories
and mock feedback all read from here, which is what stops the resume, the STAR
answers and the outreach from telling three different versions of one history.

Two rules from the project's principles are enforced structurally rather than
by convention:

* **Zero fabrication.** A story must reference at least one real fact. A story
  with no ``source_fact_ids`` is stored, but flagged unverified and excluded
  from anything that grounds interview practice, because we will not coach the
  operator to repeat something that does not trace to a real fact.
* **Nothing is generated.** The operator writes their own material; this module
  only stores, retrieves and scores it. Resume extraction turns a PDF into
  editable draft facts for the operator to correct -- it does not invent them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import CorpusFact, CorpusStory

VALID_FACT_TYPES: frozenset[str] = frozenset(
    {"project", "experience", "skill", "achievement", "education"}
)


@dataclass(slots=True)
class FactInput:
    """A fact to create or update. ``metadata`` carries tech stack, dates,
    metrics and links -- whatever structured detail the operator wants kept."""

    fact_type: str
    title: str
    body: str = ""
    metadata: dict = field(default_factory=dict)

    def validated(self) -> FactInput:
        if self.fact_type not in VALID_FACT_TYPES:
            raise ValueError(
                f"fact_type must be one of {sorted(VALID_FACT_TYPES)}, got {self.fact_type!r}"
            )
        if not self.title.strip():
            raise ValueError("a fact needs a title")
        return self


@dataclass(slots=True)
class StoryInput:
    """A STAR story. ``source_fact_ids`` is what makes it verifiable."""

    title: str
    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""
    source_fact_ids: list[uuid.UUID] = field(default_factory=list)
    competency_tags: list[str] = field(default_factory=list)


def _operator_id() -> uuid.UUID:
    return get_settings().operator_id


# --------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------


def add_fact(session: Session, data: FactInput, *, user_id: uuid.UUID | None = None) -> CorpusFact:
    data.validated()
    fact = CorpusFact(
        user_id=user_id or _operator_id(),
        fact_type=data.fact_type,
        title=data.title.strip(),
        body=data.body.strip(),
        meta=data.metadata,
    )
    session.add(fact)
    session.flush()
    return fact


def update_fact(session: Session, fact_id: uuid.UUID, data: FactInput) -> CorpusFact | None:
    fact = session.get(CorpusFact, fact_id)
    if fact is None:
        return None
    data.validated()
    fact.fact_type = data.fact_type
    fact.title = data.title.strip()
    fact.body = data.body.strip()
    fact.meta = data.metadata
    session.flush()
    return fact


def delete_fact(session: Session, fact_id: uuid.UUID) -> bool:
    fact = session.get(CorpusFact, fact_id)
    if fact is None:
        return False
    session.delete(fact)
    return True


def list_facts(
    session: Session, *, fact_type: str | None = None, user_id: uuid.UUID | None = None
) -> list[CorpusFact]:
    stmt = select(CorpusFact).where(CorpusFact.user_id == (user_id or _operator_id()))
    if fact_type:
        stmt = stmt.where(CorpusFact.fact_type == fact_type)
    return list(session.scalars(stmt.order_by(CorpusFact.created_at)))


def corpus_documents(session: Session, *, user_id: uuid.UUID | None = None) -> list[str]:
    """Every fact as a match-ready document (title + body).

    This is what :func:`lighthouse.discover.match.build_index` consumes. One
    document per fact keeps the document-frequency signal meaningful -- a term
    appearing in three separate projects is stronger evidence than one repeated
    within a single blob.
    """
    return [f"{fact.title}\n{fact.body}".strip() for fact in list_facts(session, user_id=user_id)]


# --------------------------------------------------------------------------
# Stories
# --------------------------------------------------------------------------


def add_story(
    session: Session, data: StoryInput, *, user_id: uuid.UUID | None = None
) -> CorpusStory:
    if not data.title.strip():
        raise ValueError("a story needs a title")
    story = CorpusStory(
        user_id=user_id or _operator_id(),
        title=data.title.strip(),
        situation=data.situation.strip(),
        task=data.task.strip(),
        action=data.action.strip(),
        result=data.result.strip(),
        source_fact_ids=_verify_fact_ids(session, data.source_fact_ids),
        competency_tags=[t.strip().lower() for t in data.competency_tags if t.strip()],
    )
    session.add(story)
    session.flush()
    return story


def _verify_fact_ids(session: Session, fact_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Keep only ids that point at real facts.

    A story referencing a deleted or bogus fact is not grounded, so silently
    dropping the dangling reference is safer than trusting it -- the story then
    correctly reads as unverified.
    """
    if not fact_ids:
        return []
    found = set(session.scalars(select(CorpusFact.id).where(CorpusFact.id.in_(fact_ids))))
    return [fid for fid in fact_ids if fid in found]


def list_stories(session: Session, *, user_id: uuid.UUID | None = None) -> list[CorpusStory]:
    return list(
        session.scalars(
            select(CorpusStory)
            .where(CorpusStory.user_id == (user_id or _operator_id()))
            .order_by(CorpusStory.created_at)
        )
    )


def unverified_stories(session: Session, *, user_id: uuid.UUID | None = None) -> list[CorpusStory]:
    """Stories with no backing fact. Surfaced so the operator can fix them
    before they are relied on in practice."""
    return [s for s in list_stories(session, user_id=user_id) if not s.source_fact_ids]


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


@dataclass(slots=True)
class CorpusSummary:
    """A quick read on corpus health, used by onboarding and the briefing."""

    fact_count: int
    facts_by_type: dict[str, int]
    story_count: int
    unverified_story_count: int

    @property
    def is_usable_for_matching(self) -> bool:
        """Match scoring needs something to compare against. The onboarding
        target is a handful of real projects, not an empty corpus."""
        return self.fact_count >= 3

    @property
    def readiness_note(self) -> str:
        if self.fact_count == 0:
            return "Corpus is empty. Add your resume and a few projects to enable match scoring."
        if not self.is_usable_for_matching:
            return f"Only {self.fact_count} facts. Add a few more projects for reliable matching."
        note = f"{self.fact_count} facts across {len(self.facts_by_type)} categories."
        if self.unverified_story_count:
            note += f" {self.unverified_story_count} stories need a source fact."
        return note


def summarize(session: Session, *, user_id: uuid.UUID | None = None) -> CorpusSummary:
    facts = list_facts(session, user_id=user_id)
    by_type: dict[str, int] = {}
    for fact in facts:
        by_type[fact.fact_type] = by_type.get(fact.fact_type, 0) + 1
    stories = list_stories(session, user_id=user_id)
    return CorpusSummary(
        fact_count=len(facts),
        facts_by_type=by_type,
        story_count=len(stories),
        unverified_story_count=sum(1 for s in stories if not s.source_fact_ids),
    )
