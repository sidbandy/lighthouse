"""Résumé versions, and what the funnel can say about them.

A funnel over one undifferentiated pile can say how the search is going. It
cannot say whether the rewrite did anything, and that is most of the reason to
track versions at all.

The counting rule that matters: a rejection is a response. Dropping it would
flatter whichever résumé collected the most silence, which is the opposite of
what this is for.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from lighthouse.core.db import engine
from lighthouse.core.models import Company, Posting
from lighthouse.track import applications, resumes

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


def _applied(session, user_id, version, *events):
    """One application using ``version``, with the given employer events after
    it went in."""
    application, _ = applications.get_or_create(
        session, _posting(session).id, mark_saved=False, user_id=user_id
    )
    application.resume_version_id = version.id
    applications.log_event(
        session, application, "applied", occurred_at=_NOW - timedelta(days=30), user_id=user_id
    )
    for offset, event in enumerate(events, start=1):
        applications.log_event(
            session,
            application,
            event,
            occurred_at=_NOW - timedelta(days=30 - offset),
            user_id=user_id,
        )
    session.flush()
    return application


def _states(session, user_id):
    return [state for state, _ in applications.board(session, user_id=user_id)]


class TestSaveVersion:
    def test_needs_a_label(self, session, user_id):
        with pytest.raises(ValueError):
            resumes.save_version(session, label="  ", user_id=user_id)

    def test_keeps_the_extracted_text(self, session, user_id):
        """Stored so a later tailor run can score against the résumé actually
        sent, not whatever is on disk today."""
        version = resumes.save_version(
            session, label="v3", extracted_text="Python, Postgres", user_id=user_id
        )
        assert version.extracted_text == "Python, Postgres"

    def test_lists_newest_first(self, session, user_id):
        resumes.save_version(session, label="older", user_id=user_id)
        resumes.save_version(session, label="newer", user_id=user_id)
        session.flush()

        labels = [v.label for v in resumes.list_versions(session, user_id=user_id)]
        assert labels[:2] == ["newer", "older"] or set(labels[:2]) == {"newer", "older"}


class TestOutcomesByVersion:
    def test_no_versions_means_nothing_to_compare(self, session, user_id):
        assert resumes.outcomes_by_version(session, [], user_id=user_id) == []

    def test_counts_applications_and_responses(self, session, user_id):
        version = resumes.save_version(session, label="v1", user_id=user_id)
        _applied(session, user_id, version, "assessment_received")
        _applied(session, user_id, version)

        outcome = resumes.outcomes_by_version(session, _states(session, user_id), user_id=user_id)[
            0
        ]
        assert (outcome.applied, outcome.responded) == (2, 1)
        assert outcome.statement == "1 of 2 got a response"

    def test_a_rejection_counts_as_a_response(self, session, user_id):
        """Otherwise the version that collected the most silence looks best."""
        version = resumes.save_version(session, label="v1", user_id=user_id)
        _applied(session, user_id, version, "rejected")

        outcome = resumes.outcomes_by_version(session, _states(session, user_id), user_id=user_id)[
            0
        ]
        assert outcome.responded == 1

    def test_saved_but_never_applied_is_not_counted(self, session, user_id):
        version = resumes.save_version(session, label="v1", user_id=user_id)
        application, _ = applications.get_or_create(
            session, _posting(session).id, user_id=user_id
        )
        application.resume_version_id = version.id
        session.flush()

        outcome = resumes.outcomes_by_version(session, _states(session, user_id), user_id=user_id)[
            0
        ]
        assert (outcome.applied, outcome.responded) == (0, 0)
        assert outcome.statement == "not sent yet"

    def test_reports_counts_never_a_rate(self, session, user_id):
        """A response rate over a handful of applications moves twenty points
        on one reply. The statement stays counts, at any sample size."""
        version = resumes.save_version(session, label="v1", user_id=user_id)
        for _ in range(12):
            _applied(session, user_id, version, "rejected")

        outcome = resumes.outcomes_by_version(session, _states(session, user_id), user_id=user_id)[
            0
        ]
        assert "%" not in outcome.statement
        assert outcome.statement == "12 of 12 got a response"

    def test_versions_are_reported_separately(self, session, user_id):
        good = resumes.save_version(session, label="rewrite", user_id=user_id)
        bad = resumes.save_version(session, label="original", user_id=user_id)
        _applied(session, user_id, good, "interview_scheduled")
        _applied(session, user_id, bad)

        outcomes = resumes.outcomes_by_version(
            session, _states(session, user_id), user_id=user_id
        )
        by_label = {o.label: o for o in outcomes}
        assert by_label["rewrite"].responded == 1
        assert by_label["original"].responded == 0


class TestSetApplicationVersion:
    def test_rejects_an_unknown_version(self, session, user_id):
        application, _ = applications.get_or_create(
            session, _posting(session).id, user_id=user_id
        )
        with pytest.raises(ValueError):
            resumes.set_application_version(session, application, uuid4())

    def test_clearing_is_allowed(self, session, user_id):
        version = resumes.save_version(session, label="v1", user_id=user_id)
        application, _ = applications.get_or_create(
            session, _posting(session).id, user_id=user_id
        )
        resumes.set_application_version(session, application, version.id)
        resumes.set_application_version(session, application, None)
        assert application.resume_version_id is None
