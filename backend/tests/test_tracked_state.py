"""Tracked state on postings, and the transitions the client is offered.

Discover shows thousands of rows and the board holds a couple of hundred. "Have
I already applied to this?" is exactly the question the tool should never make
the operator answer from memory, so an already-tracked posting has to say so
rather than offer to save it again.

The transition table moved to the server for a related reason: the board and the
posting window both render "what can I log next", and two copies of that table
drift. One of them then offers a transition that reads as nonsense -- an offer
on something never applied to.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from lighthouse.core.db import engine
from lighthouse.core.models import Company, Posting
from lighthouse.track import applications
from lighthouse.track.applications import Stage, transitions_from
from lighthouse.track.schemas import TrackedStateOut

_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


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


def _posting(session) -> Posting:
    slug = uuid4().hex[:12]
    company = Company(name=f"Fixture Co {slug}", canonical_name=f"fixture co {slug}")
    session.add(company)
    session.flush()
    posting = Posting(
        company_id=company.id,
        title="Software Engineer Intern",
        normalized_title="software engineer",
        url=f"https://example.com/jobs/{slug}",
        canonical_url=f"https://example.com/jobs/{slug}",
    )
    session.add(posting)
    session.flush()
    return posting


class TestTransitions:
    def test_saved_can_only_go_to_applied_or_away(self):
        assert {t.event_type for t in transitions_from(Stage.SAVED)} == {"applied", "withdrawn"}

    def test_an_offer_is_not_reachable_from_saved(self):
        """The reason this table exists: nothing should offer to log an offer
        on a posting that was never applied to."""
        assert "offer" not in {t.event_type for t in transitions_from(Stage.SAVED)}

    @pytest.mark.parametrize("stage", [Stage.REJECTED, Stage.WITHDRAWN, Stage.ACCEPTED])
    def test_terminal_stages_offer_nothing(self, stage):
        assert transitions_from(stage) == []

    def test_setbacks_are_marked_but_present(self):
        """A rejection renders quieter and is never hidden -- the funnel needs
        it, and it is as real a fact as an offer."""
        applied = transitions_from(Stage.APPLIED)
        rejected = next(t for t in applied if t.event_type == "rejected")
        assert rejected.is_setback
        assert not next(t for t in applied if t.event_type == "assessment_received").is_setback

    def test_every_offered_event_is_one_the_api_accepts(self):
        """A transition the client can render but the API rejects is a dead
        button. Checked across every stage rather than spot-checked."""
        for stage in Stage:
            for transition in transitions_from(stage):
                assert transition.event_type in applications.EVENT_STAGES


class TestStatesForPostings:
    def test_untracked_postings_are_absent_not_null(self, session, user_id):
        """"Not on the board" is not a stage."""
        posting = _posting(session)
        assert applications.states_for_postings(session, [posting.id], user_id=user_id) == {}

    def test_returns_the_folded_state_for_a_tracked_posting(self, session, user_id):
        posting = _posting(session)
        application, _ = applications.get_or_create(session, posting.id, user_id=user_id)
        applications.log_event(
            session, application, "applied", occurred_at=_NOW, user_id=user_id
        )

        states = applications.states_for_postings(session, [posting.id], user_id=user_id)
        assert states[posting.id].stage is Stage.APPLIED

    def test_ignores_another_operators_applications(self, session, user_id):
        posting = _posting(session)
        applications.get_or_create(session, posting.id, user_id=uuid4())

        assert applications.states_for_postings(session, [posting.id], user_id=user_id) == {}

    def test_empty_input_does_not_query(self, session, user_id):
        assert applications.states_for_postings(session, [], user_id=user_id) == {}

    def test_mixed_page_returns_only_the_tracked_ones(self, session, user_id):
        tracked, untracked = _posting(session), _posting(session)
        applications.get_or_create(session, tracked.id, user_id=user_id)

        states = applications.states_for_postings(
            session, [tracked.id, untracked.id], user_id=user_id
        )
        assert set(states) == {tracked.id}


class TestTrackedStateOut:
    def test_carries_the_stage_and_its_valid_transitions(self, session, user_id):
        posting = _posting(session)
        application, _ = applications.get_or_create(session, posting.id, user_id=user_id)
        applications.log_event(
            session, application, "applied", occurred_at=_NOW, user_id=user_id
        )
        state = applications.states_for_postings(session, [posting.id], user_id=user_id)[
            posting.id
        ]

        out = TrackedStateOut.from_state(state)
        assert out.stage == "APPLIED"
        assert out.stage_label == "Applied"
        assert out.is_live and not out.is_terminal
        assert {t.event_type for t in out.next_events} == {
            t.event_type for t in transitions_from(Stage.APPLIED)
        }

    def test_a_closed_application_offers_nothing_further(self, session, user_id):
        posting = _posting(session)
        application, _ = applications.get_or_create(session, posting.id, user_id=user_id)
        applications.log_event(
            session, application, "rejected", occurred_at=_NOW, user_id=user_id
        )
        state = applications.states_for_postings(session, [posting.id], user_id=user_id)[
            posting.id
        ]

        out = TrackedStateOut.from_state(state)
        assert out.is_terminal
        assert out.next_events == []
