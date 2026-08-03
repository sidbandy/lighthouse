"""The funnel is where false precision would be easiest to ship, so the tests
here are mostly about what the module refuses to say.

Two rules carry the weight. The first is that a percentage below
:data:`MIN_SAMPLE` is not reported at all -- nine applications and one interview
is not an "11% interview rate", it is nine applications. The second is the
distinction between *logged at* a stage and *progressed past* it. Stage counts
once used ">= this stage", which meant an application that went straight from
applied to interview was counted as having had an assessment it never had: the
assessment row inflated, and the step out of it rendered meaningless. Counts are
exact-match; only conversions, where the question really is about depth, use the
comparison.

All of this is pure, so states are folded in memory and nothing is saved.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from lighthouse.track.applications import ApplicationState, Stage, fold
from lighthouse.track.funnel import (
    MIN_SAMPLE,
    Conversion,
    FunnelReport,
    WaitTime,
    build,
    logged_at,
    progressed_to,
)

DAY_ZERO = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
TODAY = date(2026, 7, 24)


def _state(*steps: tuple[str, int]) -> ApplicationState:
    """An application's history as (event type, days after the first step)."""
    application = SimpleNamespace(
        id=uuid4(), posting_id=uuid4(), notes=None, resume_version_id=None
    )
    return fold(
        application,
        [
            SimpleNamespace(
                event_type=event_type, payload={}, occurred_at=DAY_ZERO + timedelta(days=day)
            )
            for event_type, day in steps
        ],
    )


def _stage_count(report, stage: Stage):
    return next(s for s in report.stages if s.stage is stage)


def _conversion(report, to_label: str) -> Conversion:
    return next(c for c in report.conversions if c.to_label == to_label)


def _wait(report, to_label: str) -> WaitTime:
    return next(w for w in report.waits if w.to_label == to_label)


class TestReachedVersusProgressed:
    """The pipeline is not uniform. Plenty of roles have no online assessment,
    and treating "got further than" as "did this" invents a step."""

    def test_skipping_the_assessment_is_not_having_one(self):
        state = _state(("applied", 0), ("interview_scheduled", 14))
        assert logged_at(state, Stage.ASSESSMENT) is False
        assert progressed_to(state, Stage.INTERVIEW) is True

    def test_the_count_row_and_the_conversion_row_disagree_on_purpose(self):
        """Same application, two honest answers: it never sat an assessment, and
        it did hear back."""
        report = build([_state(("applied", 0), ("interview_scheduled", 14))])
        assert _stage_count(report, Stage.ASSESSMENT).reached == 0
        assert _stage_count(report, Stage.INTERVIEW).reached == 1
        assert _conversion(report, "heard anything back").reached_to == 1

    def test_a_rejection_is_not_depth(self):
        """REJECTED sorts above OFFER so that it wins the fold. It must not
        therefore read as having got as far as an offer."""
        state = _state(("applied", 0), ("rejected", 20))
        assert state.stage is Stage.REJECTED
        assert progressed_to(state, Stage.OFFER) is False
        assert progressed_to(state, Stage.APPLIED) is True

    def test_a_saved_job_has_not_applied(self):
        assert progressed_to(_state(("saved", 0)), Stage.APPLIED) is False


class TestConversionStatement:
    def test_below_the_threshold_no_percentage_is_offered(self):
        """The core honesty rule. A ratio from nine tries is a ratio; a
        percentage from nine tries is a claim."""
        statement = Conversion("Applied", "reached an interview", MIN_SAMPLE - 1, 3).statement
        assert statement == "3 of 9 — too few to read anything into yet"
        assert "%" not in statement

    def test_at_the_threshold_the_rate_appears(self):
        assert Conversion("Applied", "reached an interview", 12, 3).statement == "3 of 12 (25%)"
        assert Conversion("Applied", "reached an interview", MIN_SAMPLE, 1).has_enough_data is True


class TestConversionsAreMeasuredFromApplied:
    def test_every_denominator_is_the_applied_count(self):
        """A consecutive-pair rate would assume every application walks the same
        path, which is exactly the fiction this project avoids."""
        states = [_state(("applied", 0)) for _ in range(9)]
        states += [_state(("applied", 0), ("interview_scheduled", 14)) for _ in range(3)]
        report = build(states)

        assert {c.reached_from for c in report.conversions} == {12}
        assert _conversion(report, "reached an interview").statement == "3 of 12 (25%)"
        assert _conversion(report, "reached an offer").statement == "0 of 12 (0%)"


class TestWaitTimeStatement:
    def test_nothing_observed_says_so(self):
        assert WaitTime("Applied", "an interview").statement == "no observations yet"

    @pytest.mark.parametrize(
        ("days", "expected"),
        [([5], "observed: 5d (n=1)"), ([9, 3], "observed: 3d, 9d (n=2)")],
    )
    def test_a_handful_is_listed_raw(self, days, expected):
        """A median of one data point is a median in name only, and reads as far
        more settled than it is."""
        statement = WaitTime("Applied", "an interview", days).statement
        assert statement == expected
        assert "median" not in statement

    def test_three_observations_earn_a_median_with_its_range(self):
        assert (
            WaitTime("Applied", "an interview", [9, 2, 4]).statement
            == "median 4 days (n=3, range 2–9)"
        )

    def test_gaps_come_from_dates_that_exist(self):
        report = build(
            [
                _state(("applied", 0), ("interview_scheduled", 10)),
                _state(("applied", 0), ("interview_scheduled", 4)),
                _state(("applied", 0), ("rejected", 30)),
            ]
        )
        # The rejection contributes nothing: it is an outcome, not an interview.
        assert _wait(report, "an interview").days == [10, 4]
        assert _wait(report, "an offer").statement == "no observations yet"


class TestBasis:
    def test_nothing_logged_yet(self):
        assert build([]).basis() == "No applications logged yet."

    def test_below_the_threshold_the_counts_are_offered_and_the_rates_withheld(self):
        basis = FunnelReport(total=1).basis()
        assert basis.startswith("1 application so far.")
        assert "rates are not shown" in basis
        assert FunnelReport(total=3).basis().startswith("3 applications so far.")

    def test_at_the_threshold_the_sample_is_simply_stated(self):
        assert FunnelReport(total=MIN_SAMPLE).basis() == "Across 10 logged applications."


class TestBuild:
    def test_an_empty_funnel_reports_rather_than_raising(self):
        """The first thing a new operator sees."""
        report = build([])
        assert report.total == 0
        assert (report.stages, report.conversions, report.waits, report.silent) == ([], [], [], [])

    def test_silence_lists_only_applications_still_waiting(self):
        live = _state(("applied", 0))
        report = build([live, _state(("applied", 0), ("rejected", 20))], today=TODAY)
        assert report.silent == [(str(live.application_id), 53)]

    def test_current_counts_where_an_application_sits_now(self):
        report = build([_state(("applied", 0), ("interview_scheduled", 14))])
        assert _stage_count(report, Stage.APPLIED).current == 0
        assert _stage_count(report, Stage.INTERVIEW).current == 1
