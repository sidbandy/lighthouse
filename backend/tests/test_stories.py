"""The story bank: grounding, and the coverage that makes it worth opening.

Two rules carry the weight. A story is grounded only by real fact ids, so a
reference to a deleted fact has to drop rather than count -- otherwise the
unverified flag lies in the direction that matters. And competency coverage is
computed from tags the operator actually applied, never inferred from the prose:
guessing that a story "sounds like conflict" would claim a coverage they never
made, and they would find out in the room.
"""

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from lighthouse.core import corpus
from lighthouse.core.corpus import COMPETENCIES, FactInput, StoryInput
from lighthouse.core.db import engine


@pytest.fixture
def session():
    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)
    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def user_id():
    """A operator of our own, so these never touch the real corpus."""
    return uuid4()


def _fact(session, user_id, title: str):
    return corpus.add_fact(
        session, FactInput(fact_type="project", title=title, body="Built a thing."), user_id=user_id
    )


def _story(session, user_id, title: str, *, facts=(), tags=()):
    return corpus.add_story(
        session,
        StoryInput(
            title=title,
            situation="It was broken.",
            task="I had to fix it.",
            action="I fixed it.",
            result="It worked.",
            source_fact_ids=[f.id for f in facts],
            competency_tags=list(tags),
        ),
        user_id=user_id,
    )


class TestGrounding:
    def test_a_story_with_a_real_fact_is_grounded(self, session, user_id):
        fact = _fact(session, user_id, "Ingest pipeline")
        story = _story(session, user_id, "Rewrote ingest", facts=[fact])
        assert story.is_grounded
        assert story.source_fact_ids == [fact.id]

    def test_a_dangling_fact_id_is_dropped_not_trusted(self, session, user_id):
        """A reference to a fact that no longer exists is not evidence. The
        story then correctly reads as unverified rather than silently claiming
        a source."""
        story = corpus.add_story(
            session,
            StoryInput(title="Unbacked", source_fact_ids=[uuid4()]),
            user_id=user_id,
        )
        assert story.source_fact_ids == []
        assert not story.is_grounded

    def test_a_story_needs_a_title(self, session, user_id):
        with pytest.raises(ValueError):
            corpus.add_story(session, StoryInput(title="   "), user_id=user_id)

    def test_update_revalidates_the_fact_ids(self, session, user_id):
        fact = _fact(session, user_id, "Ledger service")
        story = _story(session, user_id, "Shipped ledger", facts=[fact])

        corpus.update_story(
            session,
            story.id,
            StoryInput(title="Shipped ledger", source_fact_ids=[uuid4()]),
        )
        assert story.source_fact_ids == []
        assert not story.is_grounded


class TestCompetencyCoverage:
    def test_reports_every_competency_even_with_no_stories(self, session, user_id):
        report = corpus.story_coverage(session, user_id=user_id)
        assert len(report.competencies) == len(COMPETENCIES)
        assert report.story_count == 0
        assert len(report.uncovered) == len(COMPETENCIES)
        assert "No stories yet" in report.note()

    def test_a_tag_covers_its_competency(self, session, user_id):
        _story(session, user_id, "Disagreed with a PM", tags=["conflict"])
        report = corpus.story_coverage(session, user_id=user_id)

        conflict = next(c for c in report.competencies if c.slug == "conflict")
        assert conflict.story_count == 1
        assert conflict.story_titles == ["Disagreed with a PM"]
        assert "conflict" not in {c.slug for c in report.uncovered}

    def test_coverage_is_never_inferred_from_the_prose(self, session, user_id):
        """The story is plainly about a conflict. Untagged, it counts for
        nothing -- claiming otherwise would invent a coverage the operator
        never made."""
        corpus.add_story(
            session,
            StoryInput(title="A conflict", situation="We disagreed about the schema."),
            user_id=user_id,
        )
        report = corpus.story_coverage(session, user_id=user_id)
        assert next(c for c in report.competencies if c.slug == "conflict").story_count == 0

    def test_unknown_tags_are_ignored(self, session, user_id):
        _story(session, user_id, "Odd tag", tags=["not-a-competency"])
        report = corpus.story_coverage(session, user_id=user_id)
        assert all(c.story_count == 0 for c in report.competencies)

    def test_note_names_the_gaps(self, session, user_id):
        for slug, _ in COMPETENCIES[:-1]:
            _story(session, user_id, f"Story for {slug}", tags=[slug])
        report = corpus.story_coverage(session, user_id=user_id)
        assert COMPETENCIES[-1][0] in report.note()


class TestOverReliance:
    def test_silent_below_the_sample_floor(self, session, user_id):
        """Three stories on one project is not a pattern, it is three stories."""
        fact = _fact(session, user_id, "One project")
        for i in range(3):
            _story(session, user_id, f"Story {i}", facts=[fact])

        assert corpus.story_coverage(session, user_id=user_id).reliance == []

    def test_flags_a_project_carrying_half_the_bank(self, session, user_id):
        fact = _fact(session, user_id, "The only project")
        other = _fact(session, user_id, "A second project")
        for i in range(4):
            _story(session, user_id, f"Story {i}", facts=[fact])
        _story(session, user_id, "Different", facts=[other])

        report = corpus.story_coverage(session, user_id=user_id)
        assert [(r.fact_title, r.story_count) for r in report.reliance] == [
            ("The only project", 4)
        ]

    def test_an_evenly_spread_bank_is_not_flagged(self, session, user_id):
        facts = [_fact(session, user_id, f"Project {i}") for i in range(4)]
        for i, fact in enumerate(facts):
            _story(session, user_id, f"Story {i}", facts=[fact])

        assert corpus.story_coverage(session, user_id=user_id).reliance == []

    def test_verified_count_excludes_ungrounded_stories(self, session, user_id):
        fact = _fact(session, user_id, "Real work")
        _story(session, user_id, "Grounded", facts=[fact])
        _story(session, user_id, "Floating")

        report = corpus.story_coverage(session, user_id=user_id)
        assert (report.story_count, report.verified_count) == (2, 1)
        assert "1 not tied to a corpus fact" in report.note()
