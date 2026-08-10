"""Networking: the fold, the cadence, the paste parser, and the referral split.

Most of what can go wrong here is a wrong date or a wrong count, and both are
quiet. A thank-you counted as an unanswered message marks every warm
relationship "awaiting reply" forever; a reply that fails to reset the sequence
stops the follow-up engine at exactly the moment it should start again; a
referral asked but never confirmed, counted as a referral, would flatter the
referred column with the applications that went worst.

The cadence tests drive real dates rather than mocking a clock, because the
whole feature is arithmetic on dates and mocking the arithmetic away would test
nothing.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from lighthouse.network import cadence, capture, referrals
from lighthouse.network.contacts import ContactInput, ContactState, InteractionEntry, Kind, Stage

TODAY = date(2026, 9, 1)
_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _entry(kind: Kind, days_ago: int, direction: str | None = None) -> InteractionEntry:
    return InteractionEntry(
        id=uuid4(),
        kind=kind,
        direction=direction or ("inbound" if kind is Kind.REPLY else "outbound"),
        summary="",
        occurred_at=_NOW - timedelta(days=days_ago),
    )


def _state(*entries: InteractionEntry) -> ContactState:
    return ContactState(contact_id=uuid4(), name="Fixture Person", timeline=sorted(
        entries, key=lambda e: e.occurred_at
    ))


class TestStage:
    def test_nothing_sent_is_not_contacted(self):
        assert _state().stage is Stage.NOT_CONTACTED

    def test_sent_and_silent_is_awaiting_reply(self):
        assert _state(_entry(Kind.OUTREACH, 5)).stage is Stage.AWAITING_REPLY

    def test_their_reply_puts_the_ball_with_you(self):
        state = _state(_entry(Kind.OUTREACH, 5), _entry(Kind.REPLY, 2))
        assert state.stage is Stage.IN_CONVERSATION

    def test_a_thank_you_does_not_await_anything(self):
        """It closes a loop rather than opening one. Counting it as an
        unanswered message marked every warm relationship "awaiting reply"
        forever and printed a silence note under a thread going fine."""
        state = _state(
            _entry(Kind.OUTREACH, 20),
            _entry(Kind.REPLY, 15),
            _entry(Kind.CONVERSATION, 10),
            _entry(Kind.THANK_YOU, 9),
        )
        assert state.stage is Stage.IN_CONVERSATION
        assert state.silence_note(TODAY) is None

    def test_a_confirmed_referral_wins(self):
        state = _state(_entry(Kind.OUTREACH, 30), _entry(Kind.REFERRAL_CONFIRMED, 1))
        assert state.stage is Stage.REFERRED

    def test_silence_is_a_subtraction_between_two_real_dates(self):
        state = _state(_entry(Kind.OUTREACH, 9))
        assert state.days_since_last_outbound(TODAY) == 9
        assert "9 days since you wrote" in state.silence_note(TODAY)

    def test_silent_on_day_zero(self):
        assert _state(_entry(Kind.OUTREACH, 0)).silence_note(TODAY) is None


class TestUnansweredCount:
    def test_counts_messages_since_they_last_spoke(self):
        state = _state(_entry(Kind.OUTREACH, 30), _entry(Kind.OUTREACH, 20))
        assert state.unanswered_outreach == 2

    def test_a_reply_resets_it(self):
        """Otherwise a revived thread stays permanently at its limit."""
        state = _state(
            _entry(Kind.OUTREACH, 30),
            _entry(Kind.OUTREACH, 25),
            _entry(Kind.REPLY, 20),
            _entry(Kind.OUTREACH, 10),
        )
        assert state.unanswered_outreach == 1

    def test_notes_and_thank_yous_do_not_count(self):
        state = _state(
            _entry(Kind.OUTREACH, 10), _entry(Kind.NOTE, 5), _entry(Kind.THANK_YOU, 3)
        )
        assert state.unanswered_outreach == 1


class TestCadence:
    def test_a_new_contact_is_due_now(self):
        step = cadence.next_step_for(_state(), today=TODAY).next_step
        assert step is not None and step.is_due(TODAY)

    def test_first_follow_up_is_a_week_out(self):
        step = cadence.next_step_for(_state(_entry(Kind.OUTREACH, 0)), today=TODAY).next_step
        assert step.due_on == TODAY + timedelta(days=cadence.COLD_FIRST_FOLLOWUP_DAYS)

    def test_second_follow_up_is_spaced_wider(self):
        state = _state(_entry(Kind.OUTREACH, 14), _entry(Kind.OUTREACH, 7))
        step = cadence.next_step_for(state, today=TODAY).next_step
        assert step.due_on == (_NOW - timedelta(days=7)).date() + timedelta(
            days=cadence.COLD_SECOND_FOLLOWUP_DAYS
        )

    def test_it_stops_after_the_limit(self):
        """A third follow-up does not get answered; it gets you remembered for
        the wrong reason. The engine says so and produces nothing further."""
        state = _state(
            _entry(Kind.OUTREACH, 30), _entry(Kind.OUTREACH, 20), _entry(Kind.OUTREACH, 10)
        )
        plan = cadence.next_step_for(state, today=TODAY)
        assert plan.next_step is None
        assert "limit" in plan.note

    def test_no_growing_overdue_counter_once_stopped(self):
        """Checked a year later: still one honest sentence, not a tally."""
        state = _state(
            _entry(Kind.OUTREACH, 400), _entry(Kind.OUTREACH, 380), _entry(Kind.OUTREACH, 360)
        )
        plan = cadence.next_step_for(state, today=TODAY)
        assert plan.next_step is None

    def test_a_reply_reopens_the_sequence(self):
        state = _state(
            _entry(Kind.OUTREACH, 30),
            _entry(Kind.OUTREACH, 20),
            _entry(Kind.OUTREACH, 10),
            _entry(Kind.REPLY, 1),
        )
        plan = cadence.next_step_for(state, today=TODAY)
        assert plan.next_step is not None
        assert plan.next_step.action == "Reply"

    def test_a_conversation_asks_for_a_thank_you_next(self):
        state = _state(_entry(Kind.OUTREACH, 10), _entry(Kind.CONVERSATION, 1))
        step = cadence.next_step_for(state, today=TODAY).next_step
        assert step.action == "Send a thank-you"

    def test_after_thanking_it_moves_to_an_update(self):
        state = _state(_entry(Kind.CONVERSATION, 5), _entry(Kind.THANK_YOU, 4))
        step = cadence.next_step_for(state, today=TODAY).next_step
        assert step.action == "Send an update"
        assert step.due_on > TODAY

    def test_a_confirmed_referral_ends_the_sequence(self):
        state = _state(_entry(Kind.REFERRAL_CONFIRMED, 1))
        assert cadence.next_step_for(state, today=TODAY).next_step is None

    def test_status_reads_as_a_date_not_a_score(self):
        step = cadence.NextStep("Do it", TODAY - timedelta(days=3), "because", "cold_outreach")
        assert step.status(TODAY) == "3 days late"
        assert cadence.NextStep("x", TODAY, "y", "z").status(TODAY) == "today"

    def test_the_queue_is_only_what_is_due(self):
        due = SimpleNamespace(id=uuid4(), name="Due", company_name=None)
        later = SimpleNamespace(id=uuid4(), name="Later", company_name=None)
        rows = [
            (due, _state(_entry(Kind.OUTREACH, 30))),
            (later, _state(_entry(Kind.OUTREACH, 0))),
        ]
        names = [i.name for i in cadence.due_queue(rows, today=TODAY)]
        assert names == ["Due"]

    def test_a_horizon_looks_ahead_without_changing_what_is_due(self):
        row = (SimpleNamespace(id=uuid4(), name="Soon", company_name=None), _state(
            _entry(Kind.OUTREACH, 3)
        ))
        assert cadence.due_queue([row], today=TODAY) == []
        assert len(cadence.due_queue([row], today=TODAY, horizon_days=7)) == 1


class TestPasteParser:
    def test_reads_the_usual_shape(self):
        parsed = capture.parse_pasted_contacts(
            "Jane Doe\nSoftware Engineer at Optiver\nAustin, Texas Area\n\n"
            "Marcus Lee\nQuantitative Researcher at Jane Street\nNew York, NY"
        )
        assert [(p.name, p.company_name) for p in parsed] == [
            ("Jane Doe", "Optiver"),
            ("Marcus Lee", "Jane Street"),
        ]

    def test_locations_are_not_people(self):
        """They pass every other test here — capitalised, no digits, right
        length — and LinkedIn puts one under every single person."""
        parsed = capture.parse_pasted_contacts(
            "Jane Doe\nEngineer at Stripe\nSan Francisco Bay Area"
        )
        assert [p.name for p in parsed] == ["Jane Doe"]

    def test_ui_noise_is_dropped(self):
        parsed = capture.parse_pasted_contacts(
            "Jane Doe\nEngineer at Stripe\n2nd degree\nConnect\nMessage"
        )
        assert len(parsed) == 1

    def test_pipe_separated_roles_work(self):
        parsed = capture.parse_pasted_contacts("Priya Raman\nProduct Manager | Figma")
        assert parsed[0].role_title == "Product Manager"
        assert parsed[0].company_name == "Figma"

    def test_a_name_with_no_role_still_comes_through(self):
        parsed = capture.parse_pasted_contacts("Chen Wei")
        assert [p.name for p in parsed] == ["Chen Wei"]

    def test_garbage_yields_nothing_rather_than_guesses(self):
        assert capture.parse_pasted_contacts("lorem ipsum 12345 dolor") == []
        assert capture.parse_pasted_contacts("") == []

    def test_an_alumni_paste_marks_the_batch(self):
        parsed = capture.parse_pasted_contacts("Jane Doe\nEngineer at Stripe")
        assert parsed[0].to_input(school="UT Austin").relationship_type == "alumni"
        assert parsed[0].to_input().relationship_type == "cold"


class TestContactInput:
    def test_a_contact_needs_a_name(self):
        with pytest.raises(ValueError):
            ContactInput(name="  ").validated()

    def test_an_unknown_relationship_is_rejected(self):
        with pytest.raises(ValueError):
            ContactInput(name="A", relationship_type="friend").validated()

    def test_strength_is_bounded(self):
        with pytest.raises(ValueError):
            ContactInput(name="A", strength=9).validated()


def _app(app_id, applied: bool, responded: bool):
    timeline = []
    if applied:
        timeline.append(SimpleNamespace(event_type="applied"))
    if responded:
        timeline.append(SimpleNamespace(event_type="rejected"))
    return SimpleNamespace(
        application_id=app_id,
        applied_at=_NOW if applied else None,
        timeline=timeline,
    )


class TestReferralSplit:
    def test_splits_by_how_you_got_in(self):
        referred_id, cold_id = uuid4(), uuid4()
        report = referrals.build(
            [_app(referred_id, True, True), _app(cold_id, True, False)], {referred_id}
        )
        assert (report.referred.applied, report.referred.responded) == (1, 1)
        assert (report.cold.applied, report.cold.responded) == (1, 0)

    def test_saved_but_never_applied_is_not_counted(self):
        report = referrals.build([_app(uuid4(), False, False)], set())
        assert report.cold.applied == 0

    def test_it_says_so_when_there_are_no_referrals_at_all(self):
        report = referrals.build([_app(uuid4(), True, True)], set())
        assert not report.is_comparable
        assert "No referred applications yet" in report.note()

    def test_it_refuses_to_compare_thin_groups(self):
        """Both sides present but small. "1 of 1 got a response" beside "0 of 2"
        reads like evidence and is not."""
        referred_id, cold_id = uuid4(), uuid4()
        report = referrals.build(
            [_app(referred_id, True, True), _app(cold_id, True, False)], {referred_id}
        )
        assert not report.is_comparable
        assert "Too few" in report.note()

    def test_no_percentage_is_ever_emitted(self):
        ids = [uuid4() for _ in range(12)]
        report = referrals.build(
            [_app(i, True, True) for i in ids], set(ids[:6])
        )
        assert "%" not in report.note()
