"""Onboarding has two rules worth pinning down. First, constraints are one row
per operator that gets rewritten, not appended to -- a second answer must not
leave a stale first answer behind. Second, "never answered" and "answered with
nothing" are different states, because the first is a step onboarding still owes
the operator and the second is a decision they already made.

The step ordering is exercised on a hand-built state rather than by driving the
whole database, so a change in step ordering fails here loudly and on its own.

DB tests run in a transaction rolled back afterwards, scoped to a fresh user_id,
so the real profile is never touched."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lighthouse.core.corpus import CorpusSummary
from lighthouse.core.db import engine
from lighthouse.core.models import OperatorProfile
from lighthouse.core.onboarding import (
    OnboardingState,
    OperatorConstraints,
    load_constraints,
    save_constraints,
)


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


def _profile_count(session, user_id) -> int:
    return session.scalar(
        select(func.count(OperatorProfile.id)).where(OperatorProfile.user_id == user_id)
    )


class TestConstraints:
    def test_round_trip_keeps_every_field(self, session, user_id):
        save_constraints(
            session,
            OperatorConstraints(
                preferred_locations=["New York", "Chicago"],
                open_to_remote=False,
                sponsorship="needs_sponsorship",
                weekly_study_hours=15,
                target_cycles=["Summer 2027", "Fall 2027"],
            ),
            user_id=user_id,
        )
        loaded = load_constraints(session, user_id=user_id)

        assert loaded.preferred_locations == ["New York", "Chicago"]
        assert loaded.target_cycles == ["Summer 2027", "Fall 2027"]
        assert loaded.open_to_remote is False
        assert loaded.sponsorship == "needs_sponsorship"
        assert loaded.weekly_study_hours == 15

    def test_blank_entries_are_dropped(self, session, user_id):
        """A form submits empty rows. Stored, they would become a location
        filter matching nothing."""
        save_constraints(
            session,
            OperatorConstraints(
                preferred_locations=["  Boston  ", "", "   "],
                target_cycles=["", "Summer 2027"],
            ),
            user_id=user_id,
        )
        loaded = load_constraints(session, user_id=user_id)

        assert loaded.preferred_locations == ["Boston"]
        assert loaded.target_cycles == ["Summer 2027"]

    def test_never_saved_is_none_not_empty(self, session, user_id):
        """Onboarding reads this absence as "still to do"; defaults papered over
        it would silently mark the step complete."""
        assert load_constraints(session, user_id=user_id) is None

    def test_saved_but_empty_is_not_none(self, session, user_id):
        save_constraints(session, OperatorConstraints(), user_id=user_id)
        loaded = load_constraints(session, user_id=user_id)

        assert loaded is not None
        assert loaded.preferred_locations == []

    def test_unknown_sponsorship_rejected(self, session, user_id):
        """Sponsorship drives a top-level filter, so a typo here would quietly
        hide postings."""
        with pytest.raises(ValueError):
            save_constraints(
                session, OperatorConstraints(sponsorship="green_card"), user_id=user_id
            )

    def test_negative_study_hours_rejected(self, session, user_id):
        with pytest.raises(ValueError):
            save_constraints(session, OperatorConstraints(weekly_study_hours=-1), user_id=user_id)

    def test_second_save_updates_the_one_row(self, session, user_id):
        """One row per operator by design: a second answer replaces the first
        rather than leaving two profiles for later readers to choose between."""
        save_constraints(
            session, OperatorConstraints(preferred_locations=["Boston"]), user_id=user_id
        )
        save_constraints(
            session,
            OperatorConstraints(preferred_locations=["Seattle"], weekly_study_hours=20),
            user_id=user_id,
        )

        assert _profile_count(session, user_id) == 1
        loaded = load_constraints(session, user_id=user_id)
        assert loaded.preferred_locations == ["Seattle"]
        assert loaded.weekly_study_hours == 20


def _state(*, fact_count: int, targets: int, constraints_set: bool) -> OnboardingState:
    return OnboardingState(
        corpus=CorpusSummary(
            fact_count=fact_count, facts_by_type={}, story_count=0, unverified_story_count=0
        ),
        target_company_count=targets,
        constraints_set=constraints_set,
    )


class TestNextStep:
    """Order matters: match scoring is meaningless until the corpus is usable,
    so nothing may jump the operator ahead of that."""

    @pytest.mark.parametrize(
        ("fact_count", "targets", "constraints_set", "expected"),
        [
            (0, 0, False, "upload_resume"),
            (0, 5, True, "upload_resume"),  # later answers never skip the corpus
            (2, 5, True, "add_projects"),  # under the matching minimum
            (3, 0, True, "pick_targets"),
            (3, 5, False, "set_constraints"),
            (3, 5, True, "complete"),
        ],
    )
    def test_progression(self, fact_count, targets, constraints_set, expected):
        state = _state(fact_count=fact_count, targets=targets, constraints_set=constraints_set)
        assert state.next_step == expected

    def test_is_complete_tracks_the_last_step(self):
        assert _state(fact_count=3, targets=1, constraints_set=True).is_complete is True
        assert _state(fact_count=3, targets=1, constraints_set=False).is_complete is False
