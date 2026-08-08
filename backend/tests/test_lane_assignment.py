"""Lane assignment, and the asymmetry that used to break it.

The three lanes exist to divide attention. That only works if all three can
actually hold something, and for a long time Safety could not: the rule for
elite companies fired on selectivity alone, while the rule for accessible ones
demanded a *corroborating* strong match before it would call anything a Safety.

The consequence was concrete. Only about one posting in twenty carries a
description, so most matches are thin; a thin match at an accessible company
fell past the Safety rule and landed in "Reach - too few comparable terms to
judge fit". An IBM posting is not a reach for anybody. Selectivity is a fact
about the company that holds whether or not a match could be computed, and both
ends of the scale now treat it that way.
"""

import pytest

from lighthouse.discover.lanes import (
    STRONG_MATCH,
    THIN_MATCH,
    Lane,
    assign_lane,
    selectivity_of,
)


class TestExtremesDecideOnSelectivity:
    def test_elite_is_a_reach_however_strong_the_match(self):
        assignment = assign_lane(match_score=100, selectivity=4, thin_evidence=False)
        assert assignment.lane is Lane.REACH

    def test_accessible_is_a_safety_however_thin_the_evidence(self):
        """The regression this module exists for: a title-only posting at an
        accessible company used to read as ambition."""
        assignment = assign_lane(match_score=0, selectivity=1, thin_evidence=True)
        assert assignment.lane is Lane.SAFETY
        assert "less competitive" in assignment.reason.lower()

    def test_the_two_rules_are_symmetric(self):
        """Neither extreme requires the match to agree with it."""
        elite = assign_lane(match_score=0, selectivity=4, thin_evidence=True)
        accessible = assign_lane(match_score=0, selectivity=1, thin_evidence=True)
        assert (elite.lane, accessible.lane) == (Lane.REACH, Lane.SAFETY)

    def test_a_safety_still_says_when_the_match_is_weak(self):
        """Placed on selectivity, but the reason does not pretend the match was
        good -- the operator reads the reason, not just the lane."""
        weak = assign_lane(match_score=THIN_MATCH - 1, selectivity=1, thin_evidence=False)
        strong = assign_lane(match_score=STRONG_MATCH + 10, selectivity=1, thin_evidence=False)
        assert weak.lane is strong.lane is Lane.SAFETY
        assert weak.reason != strong.reason
        assert "weak" in weak.reason.lower()
        assert "strong" in strong.reason.lower()


class TestMiddleOfTheScale:
    def test_a_realistic_match_at_a_realistic_bar_is_a_target(self):
        assignment = assign_lane(match_score=STRONG_MATCH, selectivity=2, thin_evidence=False)
        assert assignment.lane is Lane.TARGET

    def test_competitive_and_unproven_is_a_reach(self):
        assignment = assign_lane(match_score=100, selectivity=3, thin_evidence=True)
        assert assignment.lane is Lane.REACH
        assert "too few comparable terms" in assignment.reason

    def test_a_weak_match_mid_scale_is_a_reach(self):
        assignment = assign_lane(match_score=THIN_MATCH - 1, selectivity=2, thin_evidence=False)
        assert assignment.lane is Lane.REACH

    @pytest.mark.parametrize("selectivity", [1, 2, 3, 4])
    def test_every_selectivity_lands_somewhere(self, selectivity):
        """No combination falls through without a lane."""
        for score in (0, THIN_MATCH, STRONG_MATCH, 100):
            for thin in (True, False):
                assignment = assign_lane(
                    match_score=score, selectivity=selectivity, thin_evidence=thin
                )
                assert assignment.lane in set(Lane)
                assert assignment.reason


class TestSelectivityLookup:
    def test_an_explicit_tier_on_the_company_wins(self):
        assert selectivity_of("anything", "accessible") == 1

    def test_the_seed_table_is_consulted_next(self):
        assert selectivity_of("jane street", None) == 4
        assert selectivity_of("accenture", None) == 1

    def test_an_unknown_company_gets_the_honest_middle(self):
        assert selectivity_of("some company nobody seeded", None) == 2
