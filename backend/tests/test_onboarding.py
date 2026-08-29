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


class TestDefaultConstraints:
    """The suggestion offered to an operator who has not answered yet.

    It exists because target_cycles had no picker and was therefore saved as an
    empty list for everyone, while still seeding filters. The rule that matters
    is that a suggestion is not an answer: it must never advance the onboarding
    ladder, or the operator is marked done for a question nobody asked them."""

    def test_preselects_the_soonest_applyable_cycles(self):
        from datetime import date

        from lighthouse.core.onboarding import default_constraints
        from lighthouse.ingest.seasons import applyable_cycles

        soonest = [c.label for c in applyable_cycles(date.today())[:3]]
        chosen = default_constraints().target_cycles

        assert soonest, "there is always at least one applyable cycle"
        assert set(soonest) <= set(chosen)
        assert chosen == sorted(
            chosen, key=lambda label: [c.label for c in applyable_cycles(date.today())].index(label)
        ), "cycles stay in soonest-first order"

    def test_always_includes_the_next_summer(self):
        """The main internship cycle is not always in the soonest three. From
        August 2026 the first three are Fall 2026, Winter 2027 and Spring 2027,
        and Summer 2027 -- the cycle with ten times the postings of either
        off-cycle term -- falls off the end. A default that drops it points a
        new operator away from what they are actually recruiting for."""
        from datetime import date

        from lighthouse.core.models import Season
        from lighthouse.core.onboarding import default_constraints
        from lighthouse.ingest.seasons import applyable_cycles

        summer = next(c for c in applyable_cycles(date.today()) if c.season is Season.SUMMER)

        assert summer.label in default_constraints().target_cycles

    @pytest.mark.parametrize("month", range(1, 13))
    def test_invariants_hold_in_every_month(self, month):
        """Swept across a year because the interesting branch is seasonal: in
        some months Summer is already inside the soonest three and must not be
        appended twice, in others it is off the end and must be added. Pinning
        only today's date would leave one of those two paths untested for
        months at a time."""
        from datetime import date

        from lighthouse.core.models import Season
        from lighthouse.core.onboarding import default_constraints
        from lighthouse.ingest.seasons import applyable_cycles

        today = date(2026, month, 15)
        applyable = applyable_cycles(today)
        chosen = default_constraints(today).target_cycles

        assert len(chosen) == len(set(chosen)), "no cycle suggested twice"
        assert set(chosen) <= {c.label for c in applyable}, "never suggests a closed cycle"
        assert {c.label for c in applyable[:3]} <= set(chosen), "keeps the soonest three"

        summer = next(c for c in applyable if c.season is Season.SUMMER)
        assert summer.label in chosen, "the main internship cycle is never dropped"
        assert 3 <= len(chosen) <= 4

    def test_suggestion_matches_the_stored_shape(self):
        """Every other field takes the dataclass default, so saving the
        suggestion unchanged is a valid answer rather than a partial one."""
        from lighthouse.core.onboarding import constraints_to_dict, default_constraints

        assert set(constraints_to_dict(default_constraints())) == set(
            constraints_to_dict(OperatorConstraints())
        )

    def test_suggesting_does_not_save(self, session, user_id):
        """The absence load_constraints reports is what the ladder reads. A
        suggestion that wrote through would mark the step done silently."""
        from lighthouse.core.onboarding import default_constraints

        default_constraints()

        assert load_constraints(session, user_id=user_id) is None

    def test_state_is_unaffected_by_a_suggestion(self):
        """constraints_set tracks storage, never the suggestion."""
        from lighthouse.core.onboarding import default_constraints

        default_constraints()

        assert _state(fact_count=3, targets=5, constraints_set=False).next_step == (
            "set_constraints"
        )


class TestOnboardingPayload:
    """The suggestion is offered only while the question is open.

    Sending it alongside a saved record would let the form re-suggest cycles
    the operator had already removed, which is the same class of mistake as
    defaulting the absence away in load_constraints."""

    def test_suggested_only_before_an_answer(self, session):
        from lighthouse.core.config import get_settings
        from lighthouse.core.router import _onboarding_out

        operator = get_settings().operator_id

        # _onboarding_out reads the configured operator rather than taking a
        # user_id, so the unanswered state is established here instead of being
        # assumed. Without this the test passes only while the real operator has
        # not onboarded, and would start failing the day they do. Rolled back.
        session.query(OperatorProfile).filter(OperatorProfile.user_id == operator).delete()

        before = _onboarding_out(session)
        assert before.constraints is None
        assert before.constraints_set is False
        assert before.suggested_constraints is not None
        assert before.suggested_constraints.target_cycles

        save_constraints(
            session,
            OperatorConstraints(target_cycles=["Summer 2027"]),
            user_id=operator,
        )

        after = _onboarding_out(session)
        assert after.constraints_set is True
        assert after.constraints.target_cycles == ["Summer 2027"]
        assert after.suggested_constraints is None
