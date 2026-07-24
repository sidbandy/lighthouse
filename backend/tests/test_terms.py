"""Term resolution: evidence over confidence scores.

Every assertion here also checks *which rule* fired, because the rule name is
what the UI shows the operator. A right answer from the wrong rule is a bug
waiting to happen.
"""

from datetime import date

import pytest

from lighthouse.core.models import (
    TERM_RULE_DESCRIPTION_DATES,
    TERM_RULE_ELIGIBILITY,
    TERM_RULE_EXPLICIT_FIELD,
    TERM_RULE_TITLE,
    TERM_RULE_UNKNOWN,
    Season,
)
from lighthouse.ingest.seasons import Cycle
from lighthouse.ingest.terms import normalize_term_label, resolve_term

TODAY = date(2026, 7, 24)


class TestCascadeOrdering:
    def test_explicit_field_wins_over_title(self):
        """What the source stated beats what we can scrape from a title."""
        result = resolve_term(
            title="Intern, Summer 2028",
            explicit_terms=["Summer 2027"],
            today=TODAY,
        )
        assert result.cycle == Cycle(Season.SUMMER, 2027)
        assert result.rule == TERM_RULE_EXPLICIT_FIELD

    def test_title_wins_over_description(self):
        result = resolve_term(
            title="SWE Intern - Fall 2026",
            description="Programme runs May 2027 - August 2027.",
            today=TODAY,
        )
        assert result.cycle == Cycle(Season.FALL, 2026)
        assert result.rule == TERM_RULE_TITLE


class TestExplicitTerms:
    def test_picks_soonest_still_applyable_term(self):
        """A posting tagged for several cycles is being recruited for the
        nearest one that has not started."""
        result = resolve_term(explicit_terms=["Fall 2027", "Summer 2027"], today=TODAY)
        assert result.cycle == Cycle(Season.SUMMER, 2027)

    def test_ignores_unparseable_terms(self):
        result = resolve_term(explicit_terms=["N/A"], title="Software Intern", today=TODAY)
        assert result.rule == TERM_RULE_UNKNOWN

    def test_falls_back_to_past_terms_when_none_upcoming(self):
        result = resolve_term(explicit_terms=["Summer 2026"], today=TODAY)
        assert result.cycle == Cycle(Season.SUMMER, 2026)


class TestDescriptionDates:
    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            ("The internship runs May 2027 - August 2027.", Cycle(Season.SUMMER, 2027)),
            ("16-week co-op from January 2027 to April 2027.", Cycle(Season.SPRING, 2027)),
            ("Placement: September 2026 through December 2026.", Cycle(Season.FALL, 2026)),
            ("Runs May - August 2027 in our Austin office.", Cycle(Season.SUMMER, 2027)),
        ],
    )
    def test_parses_explicit_ranges(self, description, expected):
        result = resolve_term(description=description, today=TODAY)
        assert result.cycle == expected
        assert result.rule == TERM_RULE_DESCRIPTION_DATES

    def test_range_wrapping_new_year_infers_start_year(self):
        """ "December - March 2027" starts in 2026, not 2027."""
        result = resolve_term(description="Runs December - March 2027.", today=TODAY)
        assert result.cycle == Cycle(Season.WINTER, 2026)

    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            ("A 12-week programme starting June 2027.", Cycle(Season.SUMMER, 2027)),
            ("This co-op begins in January 2027.", Cycle(Season.SPRING, 2027)),
        ],
    )
    def test_parses_stated_start(self, description, expected):
        result = resolve_term(description=description, today=TODAY)
        assert result.cycle == expected
        assert result.rule == TERM_RULE_DESCRIPTION_DATES

    def test_records_the_triggering_text_as_evidence(self):
        result = resolve_term(
            description="The internship runs May 2027 - August 2027.", today=TODAY
        )
        assert "May 2027" in result.evidence


class TestEligibilityInference:
    def test_graduation_year_implies_prior_summer(self):
        result = resolve_term(description="Open to students graduating in 2028.", today=TODAY)
        assert result.cycle == Cycle(Season.SUMMER, 2027)
        assert result.rule == TERM_RULE_ELIGIBILITY

    def test_ignores_implausible_graduation_years(self):
        result = resolve_term(description="Alumni who graduated in 2009 welcome.", today=TODAY)
        assert result.rule == TERM_RULE_UNKNOWN

    def test_can_be_disabled(self):
        result = resolve_term(
            description="Open to students graduating in 2028.",
            today=TODAY,
            infer_from_eligibility=False,
        )
        assert result.rule == TERM_RULE_UNKNOWN


class TestUnresolved:
    def test_bare_posting_is_unknown_not_guessed(self):
        """The honest outcome when there is genuinely no signal."""
        result = resolve_term(title="Software Engineer Intern", description="Join our team!")
        assert result.cycle is None
        assert result.rule == TERM_RULE_UNKNOWN
        assert result.is_resolved is False


def test_normalize_term_label():
    assert normalize_term_label("summer '27") == "Summer 2027"
    assert normalize_term_label("N/A") is None
