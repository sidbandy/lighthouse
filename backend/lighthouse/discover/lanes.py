"""The three-lane view: reach, target, safety.

A single ranked list quietly buries ambitious applications and produces a
season of only-safe ones. Splitting by selectivity forces the operator to keep
a few genuine reaches alive alongside the realistic bulk.

Selectivity comes from a small hand-maintained company tier table, not a model
-- that is thirty lines of config, and pretending to learn it would be false
precision. Match quality comes from the corpus scoring. A posting's lane is the
combination:

* **Reach**   - highly selective, or a strong role where the match is thinner.
  Worth a shot, but not where the bulk of applications should go.
* **Target**  - a realistic match at a realistic bar. The core of the season.
* **Safety**  - a strong match at a less competitive company.

Every lane also gets a suggested weekly quota, so "apply broadly" becomes a
concrete plan rather than a vague intention.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Company selectivity tiers. Hand-maintained; the operator can edit these.
# Higher tier = more selective. Kept deliberately small and legible.
TIER_ELITE = "elite"  # FAANG-tier, top quant (Jane Street, Citadel, ...)
TIER_HIGH = "high"  # strong tech / well-known unicorns
TIER_MID = "mid"  # solid mid-size and growth companies
TIER_ACCESSIBLE = "accessible"  # smaller / less competitive
TIER_TARGET = "target"  # operator-marked target, selectivity unknown

_TIER_SELECTIVITY: dict[str, int] = {
    TIER_ELITE: 4,
    TIER_HIGH: 3,
    TIER_MID: 2,
    TIER_ACCESSIBLE: 1,
    TIER_TARGET: 2,
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
    # Accessible: strong return on a tailored application.
    "ibm": TIER_ACCESSIBLE,
    "oracle": TIER_ACCESSIBLE,
    "cisco": TIER_ACCESSIBLE,
    "dell": TIER_ACCESSIBLE,
    "accenture": TIER_ACCESSIBLE,
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
    # Highly selective companies are a reach almost regardless of match: the
    # bar is the constraint, not the fit.
    if selectivity >= 4:
        return LaneAssignment(Lane.REACH, selectivity, "Highly selective company")

    # A strong match at a less competitive company is the definition of safety.
    if selectivity <= 1 and match_score >= STRONG_MATCH and not thin_evidence:
        return LaneAssignment(Lane.SAFETY, selectivity, "Strong match, less competitive")

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
