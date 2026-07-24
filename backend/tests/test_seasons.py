"""The season resolver is what stops the tool going stale in November."""

from datetime import date

import pytest

from lighthouse.core.models import Season
from lighthouse.ingest.seasons import (
    Cycle,
    applyable_cycles,
    is_applyable,
    next_cycle_of,
    parse_cycle,
)

JULY_2026 = date(2026, 7, 24)
NOVEMBER_2026 = date(2026, 11, 15)


class TestParseCycle:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Summer 2027", Cycle(Season.SUMMER, 2027)),
            ("SWE Intern - Fall '26", Cycle(Season.FALL, 2026)),
            ("winter2027 co-op", Cycle(Season.WINTER, 2027)),
            ("Autumn 2026", Cycle(Season.FALL, 2026)),
            ("Spring 2028 Internship", Cycle(Season.SPRING, 2028)),
        ],
    )
    def test_extracts_cycle(self, text, expected):
        assert parse_cycle(text) == expected

    @pytest.mark.parametrize("text", ["Software Engineer Intern", "N/A", "", None, "2027"])
    def test_returns_none_rather_than_guessing(self, text):
        assert parse_cycle(text) is None


class TestApplyableCycles:
    def test_july_2026_offers_off_cycle_and_next_summer(self):
        """The operator's actual situation: off-cycle roles open now, plus the
        Summer 2027 cycle that quant firms open in August."""
        labels = [c.label for c in applyable_cycles(JULY_2026, horizon_months=15)]
        assert labels[:4] == ["Fall 2026", "Winter 2027", "Spring 2027", "Summer 2027"]

    def test_excludes_cycles_already_running(self):
        """Summer 2026 started in May, so it is no longer applyable in July."""
        assert "Summer 2026" not in [c.label for c in applyable_cycles(JULY_2026)]

    def test_auto_advances_with_the_calendar(self):
        """No code change should be needed when the season rolls over."""
        labels = [c.label for c in applyable_cycles(NOVEMBER_2026, horizon_months=15)]
        assert labels[0] == "Winter 2027"
        assert "Fall 2026" not in labels

    def test_horizon_trims_the_far_future(self):
        cycles = applyable_cycles(JULY_2026, horizon_months=12)
        assert all(c.start_date <= date(2027, 7, 1) for c in cycles)
        assert "Summer 2029" not in [c.label for c in cycles]

    def test_ordering_is_by_start_date(self):
        cycles = applyable_cycles(JULY_2026)
        assert cycles == sorted(cycles, key=lambda c: c.sort_key)


class TestIsApplyable:
    def test_unknown_terms_are_kept_not_dropped(self):
        """Dropping unresolved rows would silently hide real roles."""
        assert is_applyable(None, JULY_2026) is True

    def test_past_cycle_rejected(self):
        assert is_applyable(Cycle(Season.SUMMER, 2026), JULY_2026) is False

    def test_future_cycle_accepted(self):
        assert is_applyable(Cycle(Season.SUMMER, 2027), JULY_2026) is True

    def test_beyond_horizon_rejected(self):
        assert is_applyable(Cycle(Season.SUMMER, 2030), JULY_2026, horizon_months=24) is False


class TestNextCycleOf:
    def test_rolls_to_next_year_when_this_year_started(self):
        assert next_cycle_of(Season.SUMMER, JULY_2026) == Cycle(Season.SUMMER, 2027)

    def test_stays_in_year_when_not_yet_started(self):
        assert next_cycle_of(Season.FALL, JULY_2026) == Cycle(Season.FALL, 2026)
