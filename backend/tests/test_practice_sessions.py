"""The practice record: what it keeps, what it refuses to keep, and what it
refuses to call a trend.

Two of these are privacy tests rather than behaviour tests, and they are here
because the promise they defend is easy to break by accident. Practice tells the
operator that nothing they say is recorded. The moment someone adds a
``transcript`` column "just for debugging", that promise is gone and nothing
else in the suite would notice.

The rest are about the one way a trend lies: by comparing things that are not
comparable. A typed answer has no duration, and a session with no word timings
has no silence measurement — treating either as a zero would manufacture an
improvement out of a missing input, which is the same failure as inventing a
number outright.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from lighthouse.core.db import engine
from lighthouse.core.models import PracticeSession
from lighthouse.practice import delivery, sessions
from lighthouse.practice.delivery import DeliveryMetric, DeliveryReport
from lighthouse.practice.feedback import DriftFinding, StructureFinding

_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


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


def _report(*, duration: float = 90.0, words: int = 200, **metrics: float) -> DeliveryReport:
    """A delivery report with exactly the metrics named, and nothing else."""
    report = DeliveryReport(duration_sec=duration, word_count=words)
    for key, value in metrics.items():
        report.metrics.append(
            DeliveryMetric(
                key=key,
                label=delivery.METRIC_LABELS[key],
                value=value,
                unit="",
                ideal="",
                verdict="good",
                detail="",
            )
        )
    return report


def _log(session, user_id, *, days_ago: int = 0, mode: str = sessions.SPOKEN, **metrics):
    return sessions.record(
        session,
        report=_report(**metrics),
        competency="ownership",
        question="Tell me about a project you owned.",
        answer_mode=mode,
        occurred_at=_NOW - timedelta(days=days_ago),
        user_id=user_id,
    )


class TestWhatIsStored:
    def test_the_table_has_no_transcript_column(self):
        """The privacy promise, asserted structurally.

        Practice says nothing spoken is recorded or kept. This fails the moment
        a column appears that could hold what was said.
        """
        columns = {c.name for c in inspect(PracticeSession).columns}
        for forbidden in ("transcript", "answer", "text", "audio", "audio_path", "recording"):
            assert forbidden not in columns, f"{forbidden!r} would break the Practice promise"

    def test_drift_is_kept_as_a_count_not_as_claims(self, session, user_id):
        """A drift claim quotes the operator out loud — "I led a team of nine".
        The count is the useful part and the wording is the part that would make
        this a transcript by another name."""
        row = sessions.record(
            session,
            report=_report(wpm=150.0),
            drift=[
                DriftFinding(claim="nine", detail="corpus says three"),
                DriftFinding(claim="40%", detail="not in the corpus"),
            ],
            user_id=user_id,
        )
        assert row.drift_count == 2
        assert "nine" not in str(row.__dict__.values())

    def test_structure_is_kept_as_which_parts_were_present(self, session, user_id):
        row = sessions.record(
            session,
            report=_report(wpm=150.0),
            structure=[
                StructureFinding(part="situation", label="Situation", present=True, advice=""),
                StructureFinding(part="result", label="Result", present=False, advice=""),
            ],
            user_id=user_id,
        )
        assert row.structure_present == ["situation"]

    def test_a_session_too_short_to_measure_is_still_recorded(self, session, user_id):
        """A history that drops the runs that went badly is a history that
        flatters. It is recorded and marked, then excluded from the trend."""
        row = _log(session, user_id, duration=4.0, words=6)
        assert not row.is_measurable
        assert len(sessions.history(session, user_id=user_id)) == 1
        assert sessions.trends(session, user_id=user_id) == []

    def test_rejects_an_unknown_answer_mode(self, session, user_id):
        with pytest.raises(ValueError, match="answer_mode"):
            sessions.record(
                session, report=_report(), answer_mode="mimed", user_id=user_id
            )

    def test_rejects_an_unknown_kind(self, session, user_id):
        with pytest.raises(ValueError, match="kind"):
            sessions.record(session, report=_report(), kind="interpretive", user_id=user_id)


class TestTrends:
    def test_one_session_is_not_a_trend(self, session, user_id):
        _log(session, user_id, wpm=190.0)
        assert sessions.trends(session, user_id=user_id) == []

    def test_two_sessions_produce_a_trend_that_says_it_is_early(self, session, user_id):
        _log(session, user_id, days_ago=2, wpm=190.0)
        _log(session, user_id, days_ago=0, wpm=160.0)

        pace = next(t for t in sessions.trends(session, user_id=user_id) if t.key == "wpm")
        assert pace.first == 190.0
        assert pace.latest == 160.0
        assert "not a trend yet" in pace.statement()

    def test_oldest_first_so_first_really_is_first(self, session, user_id):
        """Recorded out of order on purpose: the trend reads chronologically,
        not in insertion order."""
        _log(session, user_id, days_ago=0, wpm=120.0)
        _log(session, user_id, days_ago=9, wpm=200.0)
        _log(session, user_id, days_ago=4, wpm=160.0)

        pace = next(t for t in sessions.trends(session, user_id=user_id) if t.key == "wpm")
        assert (pace.first, pace.latest) == (200.0, 120.0)
        assert pace.sessions == 3
        assert "down" in pace.statement()

    def test_typed_answers_never_enter_a_trend(self, session, user_id):
        """There is no duration for typed text, so its pace is not the same
        measurement. Recorded, and kept out of the line."""
        _log(session, user_id, days_ago=3, wpm=180.0)
        _log(session, user_id, days_ago=2, mode=sessions.TYPED, wpm=999.0)
        _log(session, user_id, days_ago=1, wpm=150.0)

        assert len(sessions.history(session, user_id=user_id)) == 3
        pace = next(t for t in sessions.trends(session, user_id=user_id) if t.key == "wpm")
        assert pace.sessions == 2
        assert (pace.first, pace.latest) == (180.0, 150.0)

    def test_a_typed_session_stores_no_duration(self, session, user_id):
        row = _log(session, user_id, mode=sessions.TYPED, wpm=150.0)
        assert row.duration_sec is None

    def test_a_missing_metric_is_skipped_rather_than_counted_as_zero(self, session, user_id):
        """``silences`` only exists when the transcriber produced word timings.
        Two sessions with it and one without is a two-point silence trend — not
        a three-point one with an invented zero in the middle, which would read
        as a dramatic improvement that never happened."""
        _log(session, user_id, days_ago=3, wpm=150.0, silences=4.0)
        _log(session, user_id, days_ago=2, wpm=150.0)  # no word timings
        _log(session, user_id, days_ago=1, wpm=150.0, silences=3.0)

        tracked = {t.key: t for t in sessions.trends(session, user_id=user_id)}
        assert tracked["silences"].sessions == 2
        assert (tracked["silences"].first, tracked["silences"].latest) == (4.0, 3.0)
        assert tracked["wpm"].sessions == 3

    def test_a_metric_nobody_logged_produces_no_trend(self, session, user_id):
        _log(session, user_id, days_ago=2, wpm=150.0)
        _log(session, user_id, days_ago=1, wpm=140.0)
        assert {t.key for t in sessions.trends(session, user_id=user_id)} == {"wpm"}

    def test_trends_are_scoped_to_one_operator(self, session, user_id):
        other = uuid4()
        _log(session, user_id, days_ago=2, wpm=150.0)
        _log(session, user_id, days_ago=1, wpm=140.0)
        _log(session, other, days_ago=1, wpm=999.0)

        pace = next(t for t in sessions.trends(session, user_id=user_id) if t.key == "wpm")
        assert pace.sessions == 2


class TestStructureHabits:
    PARTS = ["situation", "task", "action", "result"]

    def _answer(self, session, user_id, *present: str, days_ago: int = 0):
        return sessions.record(
            session,
            report=_report(wpm=150.0),
            structure=[
                StructureFinding(part=p, label=p.title(), present=p in present, advice="")
                for p in self.PARTS
            ],
            occurred_at=_NOW - timedelta(days=days_ago),
            user_id=user_id,
        )

    def test_no_sessions_yields_nothing_rather_than_four_zeroes(self, session, user_id):
        assert sessions.structure_habits(session, parts=self.PARTS, user_id=user_id) == []

    def test_the_part_most_often_dropped_comes_first(self, session, user_id):
        """The whole point: a missing Result is invisible in any one session and
        obvious across four."""
        for day in range(4):
            self._answer(session, user_id, "situation", "task", "action", days_ago=day)

        habits = sessions.structure_habits(session, parts=self.PARTS, user_id=user_id)
        assert habits[0].part == "result"
        assert (habits[0].present, habits[0].total) == (0, 4)
        assert "0 of your last 4" in habits[0].statement()

    def test_a_thin_record_says_it_is_thin(self, session, user_id):
        self._answer(session, user_id, "situation", days_ago=1)
        habits = sessions.structure_habits(session, parts=self.PARTS, user_id=user_id)
        assert "too few to read yet" in habits[0].statement()

    def test_unmeasurable_sessions_do_not_count_toward_the_habit(self, session, user_id):
        """A four-word answer contains no Result because it contains nothing."""
        self._answer(session, user_id, "situation", "task", "action", "result", days_ago=1)
        sessions.record(
            session,
            report=_report(duration=3.0, words=4),
            structure=[
                StructureFinding(part=p, label=p.title(), present=False, advice="")
                for p in self.PARTS
            ],
            user_id=user_id,
        )
        habits = sessions.structure_habits(session, parts=self.PARTS, user_id=user_id)
        assert all(h.total == 1 for h in habits)
