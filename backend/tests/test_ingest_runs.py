"""The run-level record.

`source_health` is written per source, so it cannot answer "did the run
finish": a job killed halfway leaves every source it reached looking healthy.
That was the live failure mode -- the scheduled ingest running past the CI
timeout while health still reported ninety good sources.

The distinction these tests protect is between the three ways a run ends.
Finished stamps finished_at. Failed stamps finished_at and an error. Killed
stamps neither, which is what makes it visible as killed rather than as a run
that never happened."""

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from lighthouse.core.db import engine
from lighthouse.core.models import IngestRun
from lighthouse.ingest.pipeline import _close_run, _open_run, run_ingest


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
def bookkeeping(session):
    """Stands in for the independent transaction the run record normally uses.

    In production those commit, which is the whole point -- a killed process
    must still leave the row. Here they are folded into the test's own
    transaction so nothing reaches the real database."""

    @contextmanager
    def factory():
        yield session
        session.flush()

    return factory


def runs(session) -> list[IngestRun]:
    return list(session.scalars(select(IngestRun).order_by(IngestRun.started_at)))


class TestRunRecord:
    def test_opening_a_run_records_it_before_any_work(self, session, bookkeeping):
        run_id = _open_run(2, bookkeeping)

        (run,) = [r for r in runs(session) if r.id == run_id]
        assert run.started_at is not None
        assert run.finished_at is None
        assert run.max_tier == 2

    def test_a_finished_run_carries_its_totals(self, session, bookkeeping):
        from lighthouse.ingest.pipeline import IngestReport, SourceResult

        run_id = _open_run(2, bookkeeping)
        report = IngestReport(started_at=datetime.now(UTC))
        report.raw_count = 120
        report.merged_count = 100
        report.created = 30
        report.updated = 70
        report.skipped_not_applyable = 5
        report.collapsed_in_batch = 1
        report.sources = [
            SourceResult(source_id="a", ok=True, row_count=60),
            SourceResult(source_id="b", ok=False, row_count=0, error="boom"),
        ]

        _close_run(run_id, bookkeeping, report=report)

        run = session.get(IngestRun, run_id)
        assert run.finished_at is not None
        assert run.error is None
        assert (run.raw_count, run.merged_count) == (120, 100)
        assert (run.created, run.updated) == (30, 70)
        assert run.skipped_not_applyable == 5
        assert run.collapsed_in_batch == 1
        assert (run.sources_ok, run.sources_total) == (1, 2)
        assert run.duration_seconds >= 0
        assert run.died_without_finishing is False

    def test_a_failed_run_records_why(self, session, bookkeeping):
        run_id = _open_run(2, bookkeeping)

        _close_run(run_id, bookkeeping, error="RuntimeError: upstream gone")

        run = session.get(IngestRun, run_id)
        assert run.finished_at is not None
        assert run.error == "RuntimeError: upstream gone"
        assert run.died_without_finishing is False

    def test_a_killed_run_stays_visibly_unfinished(self, session, bookkeeping):
        """The CI-timeout case. Nothing gets to stamp the row, so it keeps a
        null finished_at and a null error -- which is what distinguishes it
        from a run that failed and from a run that never started."""
        run_id = _open_run(2, bookkeeping)

        run = session.get(IngestRun, run_id)
        assert run.finished_at is None
        assert run.error is None
        assert run.died_without_finishing is True
        assert run.duration_seconds is None

    def test_closing_an_unrecorded_run_is_a_no_op(self, session, bookkeeping):
        """_open_run returns None if bookkeeping failed. That must not then
        take down the ingest it was only observing."""
        _close_run(None, bookkeeping, error="ignored")


class TestRunIngestIntegration:
    def test_a_successful_run_is_opened_and_closed(self, session, bookkeeping):
        before = {r.id for r in runs(session)}

        report = run_ingest(session, connectors=[], run_session_factory=bookkeeping)

        (run,) = [r for r in runs(session) if r.id not in before]
        assert run.finished_at is not None
        assert run.error is None
        assert run.sources_total == 0
        assert report.created == 0

    def test_one_bad_connector_does_not_fail_the_run(self, session, bookkeeping):
        """Isolation is a property the pipeline promises: a source that 404s or
        changes layout is recorded unhealthy and skipped, and every other
        source still lands. So a connector raising is a healthy run with a
        failed source, not a failed run."""
        before = {r.id for r in runs(session)}

        class Exploding:
            source_id = "exploding"

            def fetch(self, *a, **k):
                raise RuntimeError("connector exploded")

        report = run_ingest(session, connectors=[Exploding()], run_session_factory=bookkeeping)

        (run,) = [r for r in runs(session) if r.id not in before]
        assert run.finished_at is not None
        assert run.error is None
        assert (run.sources_ok, run.sources_total) == (0, 1)
        assert len(report.failed_sources) == 1

    def test_a_crashing_run_records_the_error_and_still_raises(
        self, session, bookkeeping, monkeypatch
    ):
        """A failure outside the per-source guard -- the database going away
        mid-write, say -- does end the run. The record must catch that on the
        way past without swallowing it: it is an observer, not a handler."""
        before = {r.id for r in runs(session)}

        def explode(*args, **kwargs):
            raise RuntimeError("write path exploded")

        monkeypatch.setattr("lighthouse.ingest.pipeline.persist", explode)

        with pytest.raises(RuntimeError, match="write path exploded"):
            run_ingest(session, connectors=[], run_session_factory=bookkeeping)

        (run,) = [r for r in runs(session) if r.id not in before]
        assert run.finished_at is not None
        assert "write path exploded" in run.error
        assert run.died_without_finishing is False
