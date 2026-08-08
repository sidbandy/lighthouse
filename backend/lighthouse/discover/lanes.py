"""Assigns postings to reach / target / safety.

Selectivity comes from a small hand-maintained tier table rather than a model --
thirty lines of config, where pretending to learn it would be false precision.
Match quality comes from the corpus. Each lane carries a suggested weekly quota.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# How hard a company is to get into. Says nothing about whether the operator
# wants to work there -- that lives in operator_targets. Hand-maintained; higher
# is more selective.
TIER_ELITE = "elite"  # FAANG-tier, top quant (Jane Street, Citadel, ...)
TIER_HIGH = "high"  # strong tech / well-known unicorns
TIER_MID = "mid"  # solid mid-size and growth companies
TIER_ACCESSIBLE = "accessible"  # smaller / less competitive

_TIER_SELECTIVITY: dict[str, int] = {
    TIER_ELITE: 4,
    TIER_HIGH: 3,
    TIER_MID: 2,
    TIER_ACCESSIBLE: 1,
}

# Seed tiers for companies that dominate a campus search. Keyed by canonical
# name (see ingest.normalize.canonical_company). Everything unlisted is treated
# as mid selectivity, which is the honest default for an unknown company.
SEED_TIERS: dict[str, str] = {
    # Elite: the firms with the lowest acceptance rates.
    "jane street": TIER_ELITE,
    "citadel": TIER_ELITE,
    "citadel securities": TIER_ELITE,
    "hudson river trading": TIER_ELITE,
    "two sigma": TIER_ELITE,
    "de shaw": TIER_ELITE,
    "optiver": TIER_ELITE,
    "jump trading": TIER_ELITE,
    "imc trading": TIER_ELITE,
    "drw": TIER_ELITE,
    "google": TIER_ELITE,
    "meta": TIER_ELITE,
    "apple": TIER_ELITE,
    "openai": TIER_ELITE,
    "anthropic": TIER_ELITE,
    "nvidia": TIER_ELITE,
    "netflix": TIER_ELITE,
    "spacex": TIER_ELITE,
    "point72": TIER_ELITE,
    "susquehanna": TIER_ELITE,
    "five rings capital": TIER_ELITE,
    "radix trading": TIER_ELITE,
    "old mission capital": TIER_ELITE,
    "akuna capital": TIER_ELITE,
    "belvedere trading": TIER_ELITE,
    "tower research capital": TIER_ELITE,
    "millennium": TIER_ELITE,
    "aqr capital management": TIER_ELITE,
    "mckinsey and company": TIER_ELITE,
    "bain and company": TIER_ELITE,
    "boston consulting group": TIER_ELITE,
    # High: strong, well-known, still very competitive.
    "stripe": TIER_HIGH,
    "databricks": TIER_HIGH,
    "airbnb": TIER_HIGH,
    "coinbase": TIER_HIGH,
    "palantir": TIER_HIGH,
    "snowflake": TIER_HIGH,
    "datadog": TIER_HIGH,
    "cloudflare": TIER_HIGH,
    "robinhood": TIER_HIGH,
    "ramp": TIER_HIGH,
    "figma": TIER_HIGH,
    "doordash": TIER_HIGH,
    "amazon": TIER_HIGH,
    "microsoft": TIER_HIGH,
    "tiktok": TIER_HIGH,
    "bytedance": TIER_HIGH,
    "tesla": TIER_HIGH,
    "anduril": TIER_HIGH,
    "neuralink": TIER_HIGH,
    "etched": TIER_HIGH,
    "astranis": TIER_HIGH,
    "zipline": TIER_HIGH,
    "rocket lab": TIER_HIGH,
    "goldman sachs": TIER_HIGH,
    "jp morgan": TIER_HIGH,
    "morgan stanley": TIER_HIGH,
    "deloitte": TIER_HIGH,
    # Mid is the default and needs no entries. Listed here only where a company
    # would otherwise be read as more or less selective than it is.
    "bosch": TIER_MID,
    "red bull": TIER_MID,
    "western digital": TIER_MID,
    "veeva systems": TIER_MID,
    "abbvie": TIER_MID,
    "nbcuniversal": TIER_MID,
    "smiths detection": TIER_MID,
    # Accessible: hire at volume, and a tailored application genuinely converts.
    # This end of the table is what makes the Safety lane exist at all, so it is
    # kept populated deliberately -- a lane that is structurally always empty
    # teaches the operator to stop looking at it.
    "ibm": TIER_ACCESSIBLE,
    "oracle": TIER_ACCESSIBLE,
    "cisco": TIER_ACCESSIBLE,
    "dell": TIER_ACCESSIBLE,
    "accenture": TIER_ACCESSIBLE,
    "leidos": TIER_ACCESSIBLE,
    "peraton": TIER_ACCESSIBLE,
    "booz allen hamilton": TIER_ACCESSIBLE,
    "general dynamics": TIER_ACCESSIBLE,
    "saic": TIER_ACCESSIBLE,
    "caci": TIER_ACCESSIBLE,
    "mantech": TIER_ACCESSIBLE,
    "northrop grumman": TIER_ACCESSIBLE,
    "l3harris": TIER_ACCESSIBLE,
    "rtx": TIER_ACCESSIBLE,
    "boeing": TIER_ACCESSIBLE,
    "lockheed martin": TIER_ACCESSIBLE,
    "general electric": TIER_ACCESSIBLE,
    "honeywell": TIER_ACCESSIBLE,
    "cognizant": TIER_ACCESSIBLE,
    "infosys": TIER_ACCESSIBLE,
    "capgemini": TIER_ACCESSIBLE,
    "dxc technology": TIER_ACCESSIBLE,
    "innodata": TIER_ACCESSIBLE,
    "usm business systems": TIER_ACCESSIBLE,
    "welo global": TIER_ACCESSIBLE,
    "jobs for humanity": TIER_ACCESSIBLE,
}

# A match at or above this reads as strong; below the lower bound reads as thin.
STRONG_MATCH = 45
THIN_MATCH = 20


class Lane(StrEnum):
    REACH = "reach"
    TARGET = "target"
    SAFETY = "safety"


# Suggested weekly application quota per lane. Reaches are worth keeping alive
# but not the bulk of the effort; targets are the core; a couple of safeties a
# week keep the funnel honest.
WEEKLY_QUOTA: dict[Lane, int] = {
    Lane.REACH: 3,
    Lane.TARGET: 6,
    Lane.SAFETY: 2,
}


@dataclass(slots=True)
class LaneAssignment:
    lane: Lane
    selectivity: int
    reason: str


def selectivity_of(canonical_name: str, tier: str | None) -> int:
    """Selectivity 1-4 for a company.

    An explicit tier on the company row wins (the operator can override); then
    the seed table; then the honest default of mid.
    """
    if tier and tier in _TIER_SELECTIVITY:
        return _TIER_SELECTIVITY[tier]
    return _TIER_SELECTIVITY.get(SEED_TIERS.get(canonical_name, TIER_MID), 2)


def assign_lane(*, match_score: int, selectivity: int, thin_evidence: bool) -> LaneAssignment:
    """Place a posting in a lane from its match and the company's selectivity.

    The rules are legible on purpose -- the operator can see exactly why a
    posting landed where it did, which the honesty principle requires.
    """
    # The two extremes of selectivity decide on their own, because at both ends
    # the bar is the thing that determines the outcome and the match is not.
    # These are symmetric on purpose: an earlier version let a highly selective
    # company mean Reach whatever the evidence, but required a *corroborating*
    # strong match before calling anything a Safety. The result was that a
    # title-only posting at an accessible company fell through to "Reach - too
    # few comparable terms to judge fit", which reads as ambition and is simply
    # wrong. Selectivity is a fact about the company that holds whether or not
    # a match could be computed.
    if selectivity >= 4:
        return LaneAssignment(Lane.REACH, selectivity, "Highly selective company")

    if selectivity <= 1:
        if thin_evidence:
            return LaneAssignment(
                Lane.SAFETY, selectivity, "Less competitive; too little text to judge fit"
            )
        if match_score >= STRONG_MATCH:
            return LaneAssignment(Lane.SAFETY, selectivity, "Strong match, less competitive")
        return LaneAssignment(
            Lane.SAFETY, selectivity, "Less competitive, though the match is weak"
        )

    # A competitive company where the match cannot be trusted is a reach --
    # separating "few comparable terms" from "genuinely weak match", because
    # they mean different things to the operator.
    if selectivity >= 3:
        if thin_evidence:
            return LaneAssignment(
                Lane.REACH, selectivity, "Competitive; too few comparable terms to judge fit"
            )
        if match_score < STRONG_MATCH:
            return LaneAssignment(
                Lane.REACH, selectivity, "Competitive, and the match is not strong"
            )

    # A weak match anywhere leans reach: it will take work to be credible.
    if thin_evidence:
        return LaneAssignment(Lane.REACH, selectivity, "Too few comparable terms to judge fit")
    if match_score < THIN_MATCH:
        return LaneAssignment(Lane.REACH, selectivity, "Weak match on the corpus")

    return LaneAssignment(Lane.TARGET, selectivity, "Realistic match at a realistic bar")
