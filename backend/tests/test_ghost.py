"""Ghost-job signals are a checklist of observed facts, never a prediction.

A tailored application costs the operator an hour, so the panel has to be worth
trusting: every line must be something we actually checked, and the module must
never dress a guess up as a number.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from lighthouse.core.models import Posting
from lighthouse.discover.ghost import GhostLabel, Verdict, assess

TODAY = date(2026, 7, 24)
_NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _days_ago(days: int) -> datetime:
    return _NOW - timedelta(days=days)


def make_posting(
    *,
    posted_days_ago: int | None = 3,
    last_seen_days_ago: int = 0,
    updated_gap_days: int | None = 0,
    is_active: bool = True,
    description_available: bool = True,
) -> Posting:
    posted_at = None if posted_days_ago is None else _days_ago(posted_days_ago)
    source_updated_at = (
        None
        if posted_at is None or updated_gap_days is None
        else posted_at + timedelta(days=updated_gap_days)
    )
    return Posting(
        title="Software Engineer Intern",
        normalized_title="software engineer",
        url="https://boards.greenhouse.io/optiver/jobs/8003019",
        canonical_url="https://boards.greenhouse.io/optiver/jobs/8003019",
        is_active=is_active,
        description_available=description_available,
        posted_at=posted_at,
        source_updated_at=source_updated_at,
        last_seen_at=_days_ago(last_seen_days_ago),
    )


def signal_named(assessment, name: str):
    return next(s for s in assessment.signals if s.name == name)


class TestHealthyPosting:
    def test_fresh_well_corroborated_posting_is_clean(self):
        """The common case has to come back with nothing flagged, or the panel
        becomes noise the operator learns to ignore."""
        result = assess(make_posting(), source_count=4, today=TODAY)
        assert result.label is GhostLabel.LIKELY_ACTIVE
        assert result.concerns == []


class TestPostingAge:
    @pytest.mark.parametrize(
        ("age_days", "verdict"),
        [
            (0, Verdict.GOOD),
            (14, Verdict.GOOD),
            (15, Verdict.NEUTRAL),
            (45, Verdict.NEUTRAL),
            (46, Verdict.CONCERN),
            (90, Verdict.CONCERN),
            (200, Verdict.CONCERN),
        ],
    )
    def test_age_buckets(self, age_days, verdict):
        posting = make_posting(posted_days_ago=age_days)
        signal = signal_named(assess(posting, source_count=3, today=TODAY), "Posting age")
        assert signal.verdict is verdict

    @pytest.mark.parametrize("age_days", [7, 30, 62, 400])
    def test_detail_states_the_observed_day_count(self, age_days):
        """The operator judges the conclusion from the fact, so the fact has to
        be in the sentence."""
        posting = make_posting(posted_days_ago=age_days)
        signal = signal_named(assess(posting, source_count=3, today=TODAY), "Posting age")
        assert f"Posted {age_days} days ago" in signal.detail

    def test_missing_date_is_unknown_not_a_concern(self):
        """No date is an absence of evidence; treating it as a warning would
        penalise every title-only GitHub row."""
        posting = make_posting(posted_days_ago=None)
        signal = signal_named(assess(posting, source_count=3, today=TODAY), "Posting age")
        assert signal.verdict is Verdict.UNKNOWN
        assert "No posting date available" in signal.detail


class TestClosedBySource:
    def test_closed_posting_raises_a_concern(self):
        posting = make_posting(is_active=False)
        signal = signal_named(assess(posting, source_count=4, today=TODAY), "Source status")
        assert signal.verdict is Verdict.CONCERN

    def test_closed_signal_is_listed_first(self):
        """It is the strongest fact on the panel; below the fold it may as well
        not be there."""
        result = assess(make_posting(is_active=False), source_count=4, today=TODAY)
        assert result.signals[0].name == "Source status"


class TestRefreshGap:
    def test_large_gap_reads_as_automated_relisting(self):
        posting = make_posting(posted_days_ago=200, updated_gap_days=120)
        signal = signal_named(assess(posting, source_count=3, today=TODAY), "Posted vs updated")
        assert signal.verdict is Verdict.CONCERN
        assert "automated re-list" in signal.detail

    def test_small_gap_is_not_flagged(self):
        posting = make_posting(posted_days_ago=60, updated_gap_days=44)
        signal = signal_named(assess(posting, source_count=3, today=TODAY), "Posted vs updated")
        assert signal.verdict is Verdict.GOOD

    def test_missing_update_timestamp_is_unknown(self):
        posting = make_posting(updated_gap_days=None)
        signal = signal_named(assess(posting, source_count=3, today=TODAY), "Posted vs updated")
        assert signal.verdict is Verdict.UNKNOWN


class TestDescriptionAvailability:
    def test_missing_description_is_neutral_not_a_concern(self):
        """A title-only row is not evidence of ghosting. It only means the match
        score rests on less, and the panel says so instead of punishing it."""
        posting = make_posting(description_available=False)
        signal = signal_named(assess(posting, source_count=4, today=TODAY), "Description")
        assert signal.verdict is Verdict.NEUTRAL
        assert "weaker evidence" in signal.detail

    def test_missing_description_does_not_change_the_label(self):
        posting = make_posting(description_available=False)
        assert assess(posting, source_count=4, today=TODAY).label is GhostLabel.LIKELY_ACTIVE


class TestCorroboration:
    @pytest.mark.parametrize(
        ("source_count", "verdict"),
        [(1, Verdict.NEUTRAL), (2, Verdict.NEUTRAL), (3, Verdict.GOOD), (7, Verdict.GOOD)],
    )
    def test_feed_count_buckets(self, source_count, verdict):
        result = assess(make_posting(), source_count=source_count, today=TODAY)
        assert signal_named(result, "Cross-source corroboration").verdict is verdict

    def test_single_sighting_is_explicitly_not_a_warning(self):
        """Plenty of real roles appear on exactly one curated list; flagging
        them would bury the genuinely rare finds."""
        result = assess(make_posting(), source_count=1, today=TODAY)
        signal = signal_named(result, "Cross-source corroboration")
        assert signal.verdict is not Verdict.CONCERN
        assert "not itself a warning" in signal.detail


class TestSummaryWording:
    def test_no_concerns(self):
        result = assess(make_posting(), source_count=4, today=TODAY)
        assert result.summary == "No warning signs found"

    def test_one_concern_is_singular(self):
        result = assess(make_posting(posted_days_ago=60), source_count=4, today=TODAY)
        assert result.summary == "1 warning sign"

    def test_several_concerns_are_plural(self):
        posting = make_posting(posted_days_ago=60, is_active=False)
        assert assess(posting, source_count=4, today=TODAY).summary == "2 warning signs"


class TestLabelEscalation:
    def test_one_concern_is_probably_fine(self):
        result = assess(make_posting(posted_days_ago=60), source_count=4, today=TODAY)
        assert len(result.concerns) == 1
        assert result.label is GhostLabel.PROBABLY_FINE

    def test_two_concerns_are_questionable(self):
        posting = make_posting(posted_days_ago=60, is_active=False)
        result = assess(posting, source_count=4, today=TODAY)
        assert len(result.concerns) == 2
        assert result.label is GhostLabel.QUESTIONABLE

    def test_three_concerns_are_likely_stale(self):
        posting = make_posting(
            posted_days_ago=200, updated_gap_days=120, last_seen_days_ago=30, is_active=False
        )
        result = assess(posting, source_count=1, today=TODAY)
        assert len(result.concerns) >= 3
        assert result.label is GhostLabel.LIKELY_STALE


_ALL_SHAPES = [
    {},
    {"posted_days_ago": None},
    {"posted_days_ago": 60},
    {"posted_days_ago": 400, "updated_gap_days": 200},
    {"last_seen_days_ago": 30},
    {"is_active": False},
    {"description_available": False},
    {"posted_days_ago": None, "updated_gap_days": None, "last_seen_days_ago": 40},
]


class TestNoFabricatedProbability:
    """The module's whole premise is that it states what was checked.

    A "73% likely ghost" would read as measured when nothing measurable exists,
    and the operator would trust it more than the facts underneath. So no output
    string may carry a percentage or the vocabulary of a prediction.
    """

    @pytest.mark.parametrize("shape", _ALL_SHAPES)
    @pytest.mark.parametrize("source_count", [0, 1, 3])
    def test_no_percentage_or_prediction_language(self, shape, source_count):
        result = assess(make_posting(**shape), source_count=source_count, today=TODAY)
        texts = [s.detail for s in result.signals] + [result.summary]
        for text in texts:
            lowered = text.lower()
            assert "%" not in text
            assert "probability" not in lowered
            assert "likely to be" not in lowered
