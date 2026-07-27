"""The corpus is the spine everything else reads from, so two rules are tested
structurally: a fact needs a valid type and title, and a story may never claim a
source fact that does not exist. Each test runs in a transaction rolled back
afterwards, and scopes to a fresh user_id, so the real corpus is never touched."""

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from lighthouse.core import corpus
from lighthouse.core.corpus import FactInput, StoryInput
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
    return uuid4()


class TestFacts:
    def test_add_and_list_round_trip(self, session, user_id):
        corpus.add_fact(
            session,
            FactInput("project", "Rate limiter", "distributed limiter in python"),
            user_id=user_id,
        )
        facts = corpus.list_facts(session, user_id=user_id)
        assert [f.title for f in facts] == ["Rate limiter"]
        assert facts[0].fact_type == "project"

    def test_invalid_fact_type_rejected(self, session, user_id):
        with pytest.raises(ValueError):
            corpus.add_fact(session, FactInput("bogus", "Title"), user_id=user_id)

    def test_empty_title_rejected(self, session, user_id):
        with pytest.raises(ValueError):
            corpus.add_fact(session, FactInput("project", "   "), user_id=user_id)

    def test_documents_are_title_then_body(self, session, user_id):
        """This string is exactly what the match index consumes."""
        corpus.add_fact(session, FactInput("project", "API", "built a rest api"), user_id=user_id)
        corpus.add_fact(session, FactInput("skill", "Python"), user_id=user_id)
        assert corpus.corpus_documents(session, user_id=user_id) == [
            "API\nbuilt a rest api",
            "Python",
        ]

    def test_update_changes_fields(self, session, user_id):
        fact = corpus.add_fact(session, FactInput("project", "Old", "old body"), user_id=user_id)
        corpus.update_fact(session, fact.id, FactInput("skill", "New", "new body"))
        refreshed = corpus.list_facts(session, user_id=user_id)[0]
        assert refreshed.fact_type == "skill"
        assert refreshed.title == "New"
        assert refreshed.body == "new body"

    def test_delete_returns_true_then_fact_is_gone(self, session, user_id):
        fact = corpus.add_fact(session, FactInput("project", "Temp"), user_id=user_id)
        assert corpus.delete_fact(session, fact.id) is True
        assert corpus.list_facts(session, user_id=user_id) == []

    def test_delete_missing_returns_false(self, session):
        assert corpus.delete_fact(session, uuid4()) is False


class TestStories:
    def test_real_source_ids_are_kept(self, session, user_id):
        fact = corpus.add_fact(session, FactInput("project", "Real work"), user_id=user_id)
        story = corpus.add_story(
            session, StoryInput("Story", source_fact_ids=[fact.id]), user_id=user_id
        )
        assert story.source_fact_ids == [fact.id]
        assert story.is_grounded is True

    def test_bogus_source_id_is_dropped(self, session, user_id):
        """Zero fabrication: a dangling reference must not survive, or the story
        would falsely read as grounded."""
        fact = corpus.add_fact(session, FactInput("project", "Real work"), user_id=user_id)
        fake = uuid4()
        story = corpus.add_story(
            session,
            StoryInput("Story", source_fact_ids=[fact.id, fake]),
            user_id=user_id,
        )
        assert fake not in story.source_fact_ids
        assert story.source_fact_ids == [fact.id]

    def test_empty_source_is_unverified(self, session, user_id):
        story = corpus.add_story(session, StoryInput("Ungrounded"), user_id=user_id)
        assert story.is_grounded is False
        unverified = corpus.unverified_stories(session, user_id=user_id)
        assert story.id in [s.id for s in unverified]


class TestSummarize:
    def test_counts_facts_and_stories(self, session, user_id):
        corpus.add_fact(session, FactInput("project", "P"), user_id=user_id)
        corpus.add_fact(session, FactInput("skill", "S"), user_id=user_id)
        corpus.add_story(session, StoryInput("Ungrounded"), user_id=user_id)
        summary = corpus.summarize(session, user_id=user_id)
        assert summary.fact_count == 2
        assert summary.facts_by_type == {"project": 1, "skill": 1}
        assert summary.story_count == 1
        assert summary.unverified_story_count == 1

    def test_usable_for_matching_flips_at_three_facts(self, session, user_id):
        assert corpus.summarize(session, user_id=user_id).is_usable_for_matching is False
        for i in range(3):
            corpus.add_fact(session, FactInput("project", f"P{i}"), user_id=user_id)
        assert corpus.summarize(session, user_id=user_id).is_usable_for_matching is True
