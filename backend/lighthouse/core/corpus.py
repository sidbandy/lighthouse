"""The operator's own facts and stories.

Everything personal reads from here, which is what stops the resume, the STAR
answers and the outreach telling three versions of one history. Two rules are
enforced structurally: a story with no ``source_fact_ids`` is flagged unverified
and excluded from interview grounding, and nothing in this module generates
content -- it stores, retrieves and scores what the operator wrote.
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


def update_story(session: Session, story_id: uuid.UUID, data: StoryInput) -> CorpusStory | None:
    story = session.get(CorpusStory, story_id)
    if story is None:
        return None
    if not data.title.strip():
        raise ValueError("a story needs a title")
    story.title = data.title.strip()
    story.situation = data.situation.strip()
    story.task = data.task.strip()
    story.action = data.action.strip()
    story.result = data.result.strip()
    story.source_fact_ids = _verify_fact_ids(session, data.source_fact_ids)
    story.competency_tags = [t.strip().lower() for t in data.competency_tags if t.strip()]
    session.flush()
    return story


def delete_story(session: Session, story_id: uuid.UUID) -> bool:
    story = session.get(CorpusStory, story_id)
    if story is None:
        return False
    session.delete(story)
    return True


def unverified_stories(session: Session, *, user_id: uuid.UUID | None = None) -> list[CorpusStory]:
    """Stories with no backing fact. Surfaced so the operator can fix them
    before they are relied on in practice."""
    return [s for s in list_stories(session, user_id=user_id) if not s.source_fact_ids]


# --------------------------------------------------------------------------
# Story coverage
# --------------------------------------------------------------------------

# The competencies behind most behavioral questions. Deliberately short: a
# question bank runs to hundreds of phrasings but tests a handful of things, and
# one strong story flexibly covers several of them. The prompts are what the
# competency actually asks for, so the operator is not guessing at a label.
COMPETENCIES: tuple[tuple[str, str], ...] = (
    ("ownership", "You took responsibility for an outcome, not just a task"),
    ("conflict", "You disagreed with someone and handled it"),
    ("ambiguity", "You made progress without clear requirements"),
    ("failure", "Something went wrong and you did something about it"),
    ("leadership", "You moved a group, with or without the title"),
    ("prioritization", "You chose what not to do, under a real constraint"),
    ("learning", "You picked something up fast because you had to"),
    ("impact", "A result you can state in numbers"),
    ("teamwork", "You worked with people who wanted different things"),
)

# Below this, "4 of 6 stories draw on one project" is not a pattern, it is a
# small number. Silence is the honest output.
_MIN_STORIES_FOR_RELIANCE = 4


@dataclass(slots=True)
class CompetencyCoverage:
    """One competency and the stories that cover it."""

    slug: str
    prompt: str
    story_titles: list[str]

    @property
    def story_count(self) -> int:
        return len(self.story_titles)


@dataclass(slots=True)
class SourceReliance:
    """One fact and how many stories lean on it."""

    fact_id: uuid.UUID
    fact_title: str
    story_count: int


@dataclass(slots=True)
class StoryCoverageReport:
    """Which competencies have a story, and which projects are carrying too
    many of them. Deterministic set logic over what the operator wrote -- it
    turns "prep behavioral" from a mood into a finite list."""

    story_count: int
    verified_count: int
    competencies: list[CompetencyCoverage]
    reliance: list[SourceReliance]

    @property
    def uncovered(self) -> list[CompetencyCoverage]:
        return [c for c in self.competencies if c.story_count == 0]

    def note(self) -> str:
        if self.story_count == 0:
            return (
                "No stories yet. Most behavioral questions are a handful of competencies "
                "asked a hundred ways, so a few good ones cover a lot of ground."
            )
        missing = self.uncovered
        parts = [f"{self.story_count} stories covering {len(self.competencies) - len(missing)} "
                 f"of {len(self.competencies)} competencies."]
        if missing:
            parts.append("No story yet for " + ", ".join(c.slug for c in missing[:3]) + ".")
        if self.verified_count < self.story_count:
            unverified = self.story_count - self.verified_count
            parts.append(f"{unverified} not tied to a corpus fact.")
        return " ".join(parts)


def story_coverage(session: Session, *, user_id: uuid.UUID | None = None) -> StoryCoverageReport:
    """Competency gaps and over-relied-on projects, from real tags only.

    A competency is covered when a story is tagged with it. Nothing is inferred
    from the prose: guessing that a story "sounds like conflict" would invent a
    coverage the operator never claimed, and they would find out in the room.
    """
    stories = list_stories(session, user_id=user_id)
    facts = {f.id: f for f in list_facts(session, user_id=user_id)}

    by_slug: dict[str, list[str]] = {slug: [] for slug, _ in COMPETENCIES}
    reliance_counts: dict[uuid.UUID, int] = {}
    for story in stories:
        for tag in story.competency_tags or []:
            if tag in by_slug:
                by_slug[tag].append(story.title)
        for fact_id in story.source_fact_ids or []:
            reliance_counts[fact_id] = reliance_counts.get(fact_id, 0) + 1

    reliance: list[SourceReliance] = []
    if len(stories) >= _MIN_STORIES_FOR_RELIANCE:
        threshold = (len(stories) + 1) // 2
        reliance = sorted(
            (
                SourceReliance(
                    fact_id=fact_id,
                    fact_title=facts[fact_id].title,
                    story_count=count,
                )
                for fact_id, count in reliance_counts.items()
                if count >= threshold and fact_id in facts
            ),
            key=lambda r: r.story_count,
            reverse=True,
        )

    return StoryCoverageReport(
        story_count=len(stories),
        verified_count=sum(1 for s in stories if s.source_fact_ids),
        competencies=[
            CompetencyCoverage(slug=slug, prompt=prompt, story_titles=by_slug[slug])
            for slug, prompt in COMPETENCIES
        ],
        reliance=reliance,
    )


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
