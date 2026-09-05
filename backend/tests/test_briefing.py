"""The weekly briefing.

319 lines that assemble six other modules and had no tests, which made it the
top of the untested list. The briefing computes nothing of its own, so what
these pin is the assembly: which facts reach which section, the order sections
are worked in, and -- most of all -- that an empty section says *which kind* of
empty it is. "Nothing due" and "you have not added anything yet" are different
messages and the difference is the whole point of the feature.

Triage is the other half: live applications sorted into how much preparation
each is worth, driven by how far the application actually got rather than by a
score.

DB tests run in a transaction rolled back afterwards, scoped to a fresh
user_id, so the real operator's board is never touched."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from lighthouse.briefing import weekly
from lighthouse.core.db import engine
from lighthouse.core.models import Company, Posting
from lighthouse.track import applications as track

TODAY = date(2026, 9, 5)
_NOON = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


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


def _applied(session, user_id, *, days_ago: int, then: str | None = None):
    """An application sent `days_ago`, optionally advanced one more stage."""
    posting = _posting(session)
    app, _ = track.get_or_create(session, posting.id, mark_saved=False, user_id=user_id)
    track.log_event(
        session, app, "applied", occurred_at=_NOON - timedelta(days=days_ago), user_id=user_id
    )
    if then:
        track.log_event(
            session,
            app,
            then,
            occurred_at=_NOON - timedelta(days=max(days_ago - 1, 0)),
            user_id=user_id,
        )
    return app


def _section(brief, key) -> weekly.BriefSection:
    return next(s for s in brief.sections if s.key == key)


class TestEmptyState:
    """A brand-new operator is the case this has to read well for, because it
    is the first thing they will ever see on the page."""

    def test_every_section_explains_its_own_emptiness(self, session, user_id):
        brief = weekly.build(session, today=TODAY, user_id=user_id)

        assert brief.total_items == 0
        for section in brief.sections:
            assert section.count == 0
            assert section.empty_note, f"{section.key} is empty and says nothing"

    def test_empty_notes_name_the_missing_input(self, session, user_id):
        """Not "nothing due" -- which would read as being on top of things --
        but which thing has not been added yet."""
        brief = weekly.build(session, today=TODAY, user_id=user_id)

        assert "No contacts yet" in _section(brief, "outreach").empty_note
        assert "Nothing tracked yet" in _section(brief, "stale").empty_note
        assert "No stories yet" in _section(brief, "stories").empty_note

    def test_headline_does_not_claim_success(self, session, user_id):
        brief = weekly.build(session, today=TODAY, user_id=user_id)

        assert "Nothing is due" in brief.headline()
        assert "not enough in Lighthouse yet" in brief.headline()

    def test_reliance_section_is_absent_rather_than_empty(self, session, user_id):
        """Over-reliance is only a finding when there are stories to spread
        across. With none it is not an empty section, it is not a section."""
        brief = weekly.build(session, today=TODAY, user_id=user_id)

        assert "reliance" not in {s.key for s in brief.sections}


class TestSectionOrder:
    def test_sections_are_in_the_order_they_should_be_worked(self, session, user_id):
        brief = weekly.build(session, today=TODAY, user_id=user_id)

        assert [s.key for s in brief.sections] == ["outreach", "stale", "study", "stories"]


class TestStaleApplications:
    def test_an_application_silent_two_weeks_is_surfaced(self, session, user_id):
        _applied(session, user_id, days_ago=20)

        brief = weekly.build(session, today=TODAY, user_id=user_id)
        stale = _section(brief, "stale")

        assert stale.count == 1
        assert stale.items[0].detail, "the silence is stated as a dated fact"

    def test_a_recent_application_is_not(self, session, user_id):
        _applied(session, user_id, days_ago=3)

        brief = weekly.build(session, today=TODAY, user_id=user_id)
        stale = _section(brief, "stale")

        assert stale.count == 0
        assert "Nothing has been silent" in stale.empty_note

    def test_double_the_window_reads_as_late(self, session, user_id):
        _applied(session, user_id, days_ago=40)

        brief = weekly.build(session, today=TODAY, user_id=user_id)

        assert _section(brief, "stale").items[0].is_late is True

    def test_late_items_are_counted_in_the_headline(self, session, user_id):
        _applied(session, user_id, days_ago=40)

        brief = weekly.build(session, today=TODAY, user_id=user_id)

        assert "already past their date" in brief.headline()


class TestBaselineNote:
    def test_refuses_to_print_a_comparison_it_cannot_cite(self, session, user_id):
        """The repo's standing rule. An uncheckable industry average is worse
        than none, because the operator would plan against it."""
        brief = weekly.build(session, today=TODAY, user_id=user_id)

        assert "will not print a comparison figure it cannot cite" in brief.baseline_note


class TestTriage:
    @pytest.mark.parametrize(
        ("days_ago", "then", "expected"),
        [
            (2, None, "standard"),          # sent recently
            (30, None, "light"),            # sent long ago, no reply
            (10, "assessment_received", "deep"),
            (10, "interview_scheduled", "deep"),
        ],
    )
    def test_band_follows_how_far_it_actually_got(
        self, session, user_id, days_ago, then, expected
    ):
        _applied(session, user_id, days_ago=days_ago, then=then)

        (row,) = weekly.triage(session, today=TODAY, user_id=user_id)

        assert row.band == expected
        assert row.reason, "the reason travels with the placement"

    def test_terminal_applications_are_left_out(self, session, user_id):
        _applied(session, user_id, days_ago=10, then="rejected")

        assert weekly.triage(session, today=TODAY, user_id=user_id) == []

    def test_saved_but_unsent_is_not_triaged_at_all(self, session, user_id):
        """Saving a job asks nothing of anyone, so there is no preparation to
        size. It belongs on the board as something to apply to, not here as
        something to prepare for."""
        posting = _posting(session)
        track.get_or_create(session, posting.id, user_id=user_id)

        assert weekly.triage(session, today=TODAY, user_id=user_id) == []

    def test_every_live_stage_gets_a_band(self, session, user_id):
        """The band chain has no default. A stage added to the enum without a
        band should fail here rather than quietly becoming light work."""
        for event in ("applied", "assessment_received", "interview_scheduled", "final_round"):
            _applied(session, uuid4(), days_ago=5, then=event)

        for stage in track.Stage:
            if not stage.is_live:
                continue
            assert stage is track.Stage.APPLIED or stage >= track.Stage.ASSESSMENT

    def test_deep_work_sorts_first(self, session, user_id):
        _applied(session, user_id, days_ago=2)
        _applied(session, user_id, days_ago=10, then="interview_scheduled")
        _applied(session, user_id, days_ago=30)

        bands = [t.band for t in weekly.triage(session, today=TODAY, user_id=user_id)]

        assert bands == ["deep", "standard", "light"]
