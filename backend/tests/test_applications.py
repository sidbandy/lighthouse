"""An application has no status column, so every rule about "where is this now"
is a rule about the fold -- and two of them are easy to get quietly wrong.

The first is precedence: a rejection has to win over the interview that preceded
it without erasing the interview, because the dates of both are what every wait
figure is later computed from. The second is whose clock silence runs on. If
adding a note counted as activity, the operator could keep a dead application
looking alive by touching it, and "31 days, no response" -- the one number this
module exists to produce -- would stop being true.

The fold takes any object with ``event_type``/``payload``/``occurred_at``, so
most of this needs no database. The tests that do run in a transaction rolled
back afterwards and scope to a fresh user_id, so real applications are untouched.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from lighthouse.core import events as event_log
from lighthouse.core.db import engine
from lighthouse.core.models import Company, Posting
from lighthouse.track import applications
from lighthouse.track.applications import Stage, fold

TODAY = date(2026, 7, 24)
_NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


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
    """An operator of our own, so these tests never read or write the real
    operator's applications."""
    return uuid4()


def _event(event_type: str, days_ago: int, note: str = ""):
    return SimpleNamespace(
        event_type=event_type,
        payload={"note": note} if note else {},
        occurred_at=_NOW - timedelta(days=days_ago),
    )


def _application():
    return SimpleNamespace(id=uuid4(), posting_id=uuid4(), notes=None, resume_version_id=None)


def _folded(*events):
    return fold(_application(), list(events))


def _posting(session) -> Posting:
    """A company and posting the real data cannot already contain."""
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


class TestStageOrdering:
    """Terminal outcomes sort above every live stage, which is the whole reason
    "highest stage reached" is a safe way to fold."""

    @pytest.mark.parametrize(
        ("stage", "terminal"),
        [
            (Stage.SAVED, False),
            (Stage.OFFER, False),
            (Stage.REJECTED, True),
            (Stage.WITHDRAWN, True),
            (Stage.ACCEPTED, True),
        ],
    )
    def test_terminal_boundary(self, stage, terminal):
        assert stage.is_terminal is terminal

    @pytest.mark.parametrize(
        ("stage", "live"),
        [
            # Saving a job asks nothing of anyone, so there is no one to chase
            # and nothing to be silent about.
            (Stage.SAVED, False),
            (Stage.APPLIED, True),
            (Stage.INTERVIEW, True),
            (Stage.OFFER, True),
            (Stage.REJECTED, False),
        ],
    )
    def test_live_boundary(self, stage, live):
        assert stage.is_live is live


class TestFold:
    def test_rejection_outranks_the_interview_it_followed(self):
        """The interview is still a fact, and the funnel counts it: an
        application rejected after interviewing did interview."""
        state = _folded(
            _event("applied", 40),
            _event("interview_scheduled", 20),
            _event("rejected", 5),
        )
        assert state.stage is Stage.REJECTED
        assert [e.stage for e in state.timeline] == [
            Stage.APPLIED,
            Stage.INTERVIEW,
            Stage.REJECTED,
        ]

    def test_unknown_event_type_cannot_change_a_stage(self):
        """A typo or a vocabulary added later must be inert rather than either
        raising or silently folding into some adjacent stage."""
        state = _folded(_event("applied", 10), _event("recruiter_liked_my_linkedin", 2))
        assert state.stage is Stage.APPLIED
        assert [e.event_type for e in state.timeline] == ["applied"]

    def test_notes_do_not_advance_the_funnel(self):
        state = _folded(_event("applied", 10), _event("note", 1, note="emailed the recruiter"))
        assert state.stage is Stage.APPLIED

    def test_no_events_is_merely_saved(self):
        assert _folded().stage is Stage.SAVED

    def test_notes_can_be_left_out(self):
        """The board renders a lot of rows and does not need the prose."""
        with_note = _folded(_event("applied", 3, note="referred by Priya"))
        assert with_note.timeline[0].note == "referred by Priya"
        stripped = fold(
            _application(), [_event("applied", 3, note="referred by Priya")], include_notes=False
        )
        assert stripped.timeline[0].note == ""


class TestDaysSilent:
    def test_a_note_today_does_not_reset_the_clock(self):
        """The operator acting is not the employer answering. If it were, an
        application could be kept looking alive by touching it."""
        state = _folded(
            _event("applied", 60),
            _event("assessment_received", 25),
            _event("note", 0, note="still nothing"),
        )
        assert state.days_silent(TODAY) == 25

    def test_with_no_employer_signal_it_runs_from_applying(self):
        state = _folded(_event("saved", 40), _event("applied", 31))
        assert state.days_silent(TODAY) == 31

    def test_terminal_applications_are_not_waiting_on_anyone(self):
        state = _folded(_event("applied", 31), _event("rejected", 2))
        assert state.days_silent(TODAY) is None

    def test_a_saved_job_is_not_silence(self):
        """Nobody has been asked for anything yet, so counting days would be
        counting the operator's own procrastination back at them."""
        assert _folded(_event("saved", 45)).days_silent(TODAY) is None


class TestSilenceNote:
    def test_wording_names_which_clock_is_running(self):
        applied_only = _folded(_event("applied", 31))
        assert applied_only.silence_note(TODAY) == "31 days since you applied, no response"

        answered_once = _folded(_event("applied", 31), _event("assessment_received", 12))
        assert answered_once.silence_note(TODAY) == "12 days since the last update, no response"

    def test_one_day_is_singular(self):
        assert _folded(_event("applied", 1)).silence_note(TODAY).startswith("1 day since")

    def test_nothing_to_say_about_a_closed_application(self):
        assert _folded(_event("applied", 31), _event("rejected", 2)).silence_note(TODAY) is None


class TestGetOrCreate:
    def test_second_call_returns_the_same_row(self, session, user_id):
        """One application per posting: applying twice to the same role is a
        mistake, not a state."""
        posting = _posting(session)
        first, created = applications.get_or_create(session, posting.id, user_id=user_id)
        assert created is True

        second, created_again = applications.get_or_create(session, posting.id, user_id=user_id)
        assert second.id == first.id
        assert created_again is False

    def test_mark_saved_false_writes_no_opening_event(self, session, user_id):
        """A synthetic "saved" stamped at now, on an application back-dated to
        last month, made the timeline claim the operator saved the job three
        weeks after applying to it."""
        posting = _posting(session)
        application, _ = applications.get_or_create(
            session, posting.id, mark_saved=False, user_id=user_id
        )
        history = event_log.history(
            session,
            entity_type=applications.ENTITY,
            entity_id=application.id,
            user_id=user_id,
        )
        assert history == []

    def test_saving_is_recorded_by_default(self, session, user_id):
        posting = _posting(session)
        application, _ = applications.get_or_create(session, posting.id, user_id=user_id)
        history = event_log.history(
            session,
            entity_type=applications.ENTITY,
            entity_id=application.id,
            user_id=user_id,
        )
        assert [e.event_type for e in history] == ["saved"]


class TestLogEvent:
    def test_unknown_event_type_is_refused(self, session, user_id):
        """The vocabulary is a closed set, and a rejected write is far better
        than an event that quietly never counts towards anything."""
        posting = _posting(session)
        application, _ = applications.get_or_create(session, posting.id, user_id=user_id)
        with pytest.raises(ValueError):
            applications.log_event(session, application, "ghosted", user_id=user_id)

    def test_note_is_part_of_the_vocabulary(self, session, user_id):
        """It carries no stage, so it is not in EVENT_STAGES, but the operator
        still has to be able to write one down."""
        posting = _posting(session)
        application, _ = applications.get_or_create(session, posting.id, user_id=user_id)
        event = applications.log_event(
            session, application, "note", note="recruiter said two weeks", user_id=user_id
        )
        assert event.payload == {"note": "recruiter said two weeks"}


class TestBoard:
    def test_pairs_folded_state_with_its_posting(self, session, user_id):
        posting = _posting(session)
        application, _ = applications.get_or_create(
            session, posting.id, mark_saved=False, user_id=user_id
        )
        applications.log_event(
            session, application, "applied", occurred_at=_NOW - timedelta(days=9), user_id=user_id
        )

        rows = applications.board(session, user_id=user_id)
        assert len(rows) == 1
        state, paired = rows[0]
        assert paired.id == posting.id
        assert state.application_id == application.id
        assert state.stage is Stage.APPLIED

    def test_most_recent_activity_leads(self, session, user_id):
        """The board is a work queue, so the thing that moved today is the
        thing to look at."""
        stale = _posting(session)
        fresh = _posting(session)
        for posting, days_ago in ((stale, 30), (fresh, 1)):
            application, _ = applications.get_or_create(
                session, posting.id, mark_saved=False, user_id=user_id
            )
            applications.log_event(
                session,
                application,
                "applied",
                occurred_at=_NOW - timedelta(days=days_ago),
                user_id=user_id,
            )

        assert [p.id for _, p in applications.board(session, user_id=user_id)] == [
            fresh.id,
            stale.id,
        ]

    def test_one_operators_board_is_not_anothers(self, session, user_id):
        posting = _posting(session)
        applications.get_or_create(session, posting.id, user_id=user_id)
        assert applications.board(session, user_id=uuid4()) == []
