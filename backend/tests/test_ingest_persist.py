"""Characterization tests for the ingest persistence step.

``persist()`` owns the only large table in the product -- 23,268 postings and
33,987 sightings -- and had no tests at all. These were written against the
row-at-a-time implementation *before* it was rewritten to batch its writes, so
that the rewrite could be checked against observed behaviour rather than
against a reading of the code. They pin what a run does, not how it does it:
counts, upsert identity, company reuse, and the sighting re-pointing rule.

Every fixture uses a UUID-derived company name and URL so a test can never
collide with, or write into, the real posting table. DB tests run in a
transaction that is rolled back afterwards."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from lighthouse.core.db import engine
from lighthouse.core.models import Company, Posting, PostingSource
from lighthouse.ingest.base import RawPosting
from lighthouse.ingest.dedup import MergedPosting
from lighthouse.ingest.pipeline import persist

TODAY = date(2026, 8, 29)


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
def tag():
    """A per-test token, so nothing here can touch a real row."""
    return uuid4().hex[:12]


def raw(
    tag: str,
    *,
    source_id: str = "src-a",
    slug: str = "a",
    company: str | None = None,
    title: str = "Software Engineering Intern",
    terms: tuple[str, ...] = ("Summer 2027",),
    **kwargs,
) -> RawPosting:
    return RawPosting(
        source_id=source_id,
        company_name=company or f"Testco {tag}",
        title=title,
        url=f"https://example-{tag}.test/jobs/{slug}",
        explicit_terms=list(terms),
        **kwargs,
    )


def merged(*raws: RawPosting) -> MergedPosting:
    return MergedPosting(primary=raws[0], members=list(raws))


def stored(session: Session, tag: str) -> list[Posting]:
    return list(
        session.scalars(
            select(Posting).where(Posting.canonical_url.like(f"%example-{tag}.test%"))
        )
    )


class TestNewPostings:
    def test_creates_a_row_with_the_merged_fields(self, session, tag):
        report = persist(session, [merged(raw(tag))], TODAY)

        assert report.created == 1
        assert report.updated == 0
        assert report.merged_count == 1

        (posting,) = stored(session, tag)
        assert posting.title == "Software Engineering Intern"
        assert posting.canonical_url.endswith("/jobs/a")
        assert posting.season.value == "summer"
        assert posting.term_year == 2027
        assert posting.is_active is True
        assert posting.last_seen_at is not None

    def test_description_availability_tracks_the_description(self, session, tag):
        persist(session, [merged(raw(tag, slug="none"))], TODAY)
        persist(
            session,
            [merged(raw(tag, slug="some", description="Build things with Python."))],
            TODAY,
        )

        by_url = {p.canonical_url[-4:]: p for p in stored(session, tag)}
        assert by_url["none"].description_available is False
        assert by_url["some"].description_available is True

    def test_records_one_sighting_per_member(self, session, tag):
        both = merged(raw(tag, source_id="src-a"), raw(tag, source_id="src-b"))

        persist(session, [both], TODAY)

        (posting,) = stored(session, tag)
        sightings = session.scalars(
            select(PostingSource).where(PostingSource.posting_id == posting.id)
        ).all()
        assert {s.source_id for s in sightings} == {"src-a", "src-b"}


class TestUpsert:
    def test_second_run_updates_rather_than_duplicates(self, session, tag):
        persist(session, [merged(raw(tag))], TODAY)
        report = persist(session, [merged(raw(tag))], TODAY)

        assert report.created == 0
        assert report.updated == 1
        assert len(stored(session, tag)) == 1

    def test_changed_fields_are_written_on_update(self, session, tag):
        persist(session, [merged(raw(tag))], TODAY)
        persist(
            session,
            [merged(raw(tag, title="Backend Engineering Intern", description="Now described."))],
            TODAY,
        )

        (posting,) = stored(session, tag)
        assert posting.title == "Backend Engineering Intern"
        assert posting.description == "Now described."
        assert posting.description_available is True

    def test_last_seen_at_advances(self, session, tag):
        persist(session, [merged(raw(tag))], TODAY)
        (posting,) = stored(session, tag)
        first = posting.last_seen_at

        persist(session, [merged(raw(tag))], TODAY)
        session.refresh(posting)

        assert posting.last_seen_at >= first

    def test_an_unchanged_row_does_not_duplicate_its_sighting(self, session, tag):
        persist(session, [merged(raw(tag))], TODAY)
        persist(session, [merged(raw(tag))], TODAY)

        (posting,) = stored(session, tag)
        sightings = session.scalars(
            select(PostingSource).where(PostingSource.posting_id == posting.id)
        ).all()
        assert len(sightings) == 1


class TestSightingRepointing:
    def test_a_sighting_moves_when_dedup_regroups_it(self, session, tag):
        """uq_source_fingerprint says a raw row belongs to exactly one posting.
        When matching improves and a row regroups onto a different canonical
        posting, the existing sighting is re-pointed, never inserted twice."""
        moving = raw(tag, source_id="src-a", slug="first")
        persist(session, [merged(moving)], TODAY)

        # Same fingerprint, now a member of a different canonical posting.
        host = raw(tag, source_id="src-b", slug="second")
        persist(session, [merged(host, moving)], TODAY)

        sightings = session.scalars(
            select(PostingSource).where(PostingSource.source_fingerprint == moving.fingerprint)
        ).all()
        assert len(sightings) == 1

        second = next(p for p in stored(session, tag) if p.canonical_url.endswith("second"))
        assert sightings[0].posting_id == second.id


class TestCompanies:
    def test_one_company_is_reused_across_postings(self, session, tag):
        persist(
            session,
            [merged(raw(tag, slug="a")), merged(raw(tag, slug="b"))],
            TODAY,
        )

        companies = session.scalars(
            select(Company).where(Company.name == f"Testco {tag}")
        ).all()
        assert len(companies) == 1

        postings = stored(session, tag)
        assert len({p.company_id for p in postings}) == 1

    def test_ats_vendor_is_backfilled_when_first_seen_without_one(self, session, tag):
        plain = raw(tag, slug="a")
        assert plain.ats_vendor is None
        persist(session, [merged(plain)], TODAY)

        greenhouse = RawPosting(
            source_id="src-a",
            company_name=f"Testco {tag}",
            title="Software Engineering Intern",
            url=f"https://boards.greenhouse.io/testco{tag}/jobs/1234567",
            explicit_terms=["Summer 2027"],
        )
        assert greenhouse.ats_vendor is not None
        persist(session, [merged(greenhouse)], TODAY)

        company = session.scalar(select(Company).where(Company.name == f"Testco {tag}"))
        assert company.ats_vendor == greenhouse.ats_vendor


class TestFiltering:
    def test_a_cycle_that_has_already_started_is_skipped(self, session, tag):
        report = persist(session, [merged(raw(tag, terms=("Summer 2026",)))], TODAY)

        assert report.skipped_not_applyable == 1
        assert report.created == 0
        assert stored(session, tag) == []

    def test_an_unresolved_term_is_kept_not_dropped(self, session, tag):
        """Dropping these would silently hide real roles, so they are stored
        with a null cycle and surfaced flagged instead."""
        report = persist(session, [merged(raw(tag, terms=()))], TODAY)

        assert report.skipped_not_applyable == 0
        assert report.created == 1
        (posting,) = stored(session, tag)
        assert posting.season is None
        assert posting.term_year is None

    def test_term_rules_are_counted(self, session, tag):
        report = persist(session, [merged(raw(tag))], TODAY)

        assert sum(report.term_rules.values()) == 1


class TestReportTotals:
    def test_counts_add_up_across_a_mixed_batch(self, session, tag):
        batch = [
            merged(raw(tag, slug="new-1")),
            merged(raw(tag, slug="new-2")),
            merged(raw(tag, slug="stale", terms=("Summer 2026",))),
        ]

        report = persist(session, batch, TODAY)

        assert report.merged_count == 3
        assert report.created == 2
        assert report.skipped_not_applyable == 1
        assert report.created + report.updated + report.skipped_not_applyable == 3

    def test_finished_at_is_stamped(self, session, tag):
        before = datetime.now(UTC)
        report = persist(session, [merged(raw(tag))], TODAY)

        assert report.finished_at is not None
        assert report.finished_at >= before


class TestDuplicateMembers:
    def test_one_source_listing_a_row_twice_does_not_abort_the_run(self, session, tag):
        """Regression. uq_source_fingerprint means a sighting belongs to one
        posting, and the row-at-a-time implementation inserted a row per member
        without collapsing members first -- so a feed that listed the same job
        twice raised UniqueViolation and took down the whole ingest, not just
        that posting. Real feeds do this; it is the same near-duplicate class
        that puts two identical cards in a lane."""
        first = raw(tag)
        second = raw(tag)
        assert first.fingerprint == second.fingerprint

        report = persist(session, [merged(first, second)], TODAY)

        assert report.created == 1
        (posting,) = stored(session, tag)
        sightings = session.scalars(
            select(PostingSource).where(PostingSource.posting_id == posting.id)
        ).all()
        assert len(sightings) == 1

    def test_two_postings_claiming_one_canonical_url_are_counted(self, session, tag):
        """Always a dedup bug upstream. Postgres refuses a statement whose
        conflict target is hit twice, so the batch collapses them -- but
        silently absorbing it would hide the bug that produced it."""
        report = persist(session, [merged(raw(tag)), merged(raw(tag))], TODAY)

        assert report.collapsed_in_batch == 1
        assert len(stored(session, tag)) == 1
