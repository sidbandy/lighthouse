"""Ghost-job signals: is this posting actually live?

A meaningful share of listings are inactive, already filled, or pure
pipeline-building. Applying to them is wasted effort, and the effort is
expensive -- a tailored application costs an hour the operator does not have.

This is deliberately **a checklist of observable facts, not a prediction**.
Each signal is something we actually checked ("posted 62 days ago", "listed on
4 separate feeds"), stated in plain language with its own verdict. The overall
label is derived from those facts and always ships with them, so the operator
can disagree with the conclusion while still seeing the evidence.

No probability is produced. We have no honest basis for one, and a fabricated
"73% likely ghost" would be worse than the raw facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum

from ..core.models import Posting

# Age thresholds in days. Roles are typically reviewed on a rolling basis, so a
# posting that has sat for two months without being refilled is a real warning.
FRESH_DAYS = 14
AGING_DAYS = 45
STALE_DAYS = 90


class Verdict(StrEnum):
    GOOD = "good"
    NEUTRAL = "neutral"
    CONCERN = "concern"
    UNKNOWN = "unknown"


class GhostLabel(StrEnum):
    LIKELY_ACTIVE = "likely_active"
    PROBABLY_FINE = "probably_fine"
    QUESTIONABLE = "questionable"
    LIKELY_STALE = "likely_stale"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class Signal:
    """One checked fact.

    ``detail`` is the observation in the operator's own terms; it is what gets
    rendered, not the verdict on its own.
    """

    name: str
    verdict: Verdict
    detail: str


@dataclass(slots=True)
class GhostAssessment:
    label: GhostLabel
    signals: list[Signal] = field(default_factory=list)

    @property
    def concerns(self) -> list[Signal]:
        return [s for s in self.signals if s.verdict is Verdict.CONCERN]

    @property
    def summary(self) -> str:
        """One line stating the count of concerns, never a score."""
        concerns = len(self.concerns)
        if self.label is GhostLabel.INSUFFICIENT_DATA:
            return "Not enough information to judge"
        if concerns == 0:
            return "No warning signs found"
        return f"{concerns} warning sign{'s' if concerns != 1 else ''}"


def _age_signal(age_days: int | None) -> Signal:
    if age_days is None:
        return Signal(
            "Posting age",
            Verdict.UNKNOWN,
            "No posting date available from any source",
        )
    if age_days <= FRESH_DAYS:
        return Signal("Posting age", Verdict.GOOD, f"Posted {age_days} days ago")
    if age_days <= AGING_DAYS:
        return Signal("Posting age", Verdict.NEUTRAL, f"Posted {age_days} days ago")
    if age_days <= STALE_DAYS:
        return Signal(
            "Posting age",
            Verdict.CONCERN,
            f"Posted {age_days} days ago, past the {AGING_DAYS}-day mark",
        )
    return Signal(
        "Posting age",
        Verdict.CONCERN,
        f"Posted {age_days} days ago; many roles close well before this",
    )


def _corroboration_signal(source_count: int) -> Signal:
    """How many independent feeds list this role.

    Weak but genuinely useful: several curated lists carrying the same role is
    mild evidence it is real, and a single sighting is not evidence against.
    """
    if source_count >= 3:
        return Signal(
            "Cross-source corroboration",
            Verdict.GOOD,
            f"Listed on {source_count} independent feeds",
        )
    if source_count == 2:
        return Signal("Cross-source corroboration", Verdict.NEUTRAL, "Listed on 2 feeds")
    return Signal(
        "Cross-source corroboration",
        Verdict.NEUTRAL,
        "Listed on 1 feed; this is common and not itself a warning",
    )


def _freshness_signal(posting: Posting, today: date) -> Signal:
    """A posting still being re-listed is being maintained by someone."""
    if posting.last_seen_at is None:
        return Signal("Still listed", Verdict.UNKNOWN, "Not seen in a completed run yet")
    days = (today - posting.last_seen_at.astimezone(UTC).date()).days
    if days <= 3:
        return Signal("Still listed", Verdict.GOOD, "Still present in the latest source refresh")
    return Signal(
        "Still listed",
        Verdict.CONCERN,
        f"Last seen in a source refresh {days} days ago",
    )


def _refresh_signal(posting: Posting) -> Signal:
    """An old posting that keeps getting touched suggests an automated refresh
    rather than active hiring."""
    if posting.posted_at is None or posting.source_updated_at is None:
        return Signal("Posted vs updated", Verdict.UNKNOWN, "No update timestamp available")
    gap = (posting.source_updated_at - posting.posted_at).days
    if gap >= AGING_DAYS:
        return Signal(
            "Posted vs updated",
            Verdict.CONCERN,
            f"Posted {gap} days before its latest refresh, which often indicates "
            "an automated re-list rather than active hiring",
        )
    return Signal("Posted vs updated", Verdict.GOOD, "No sign of automated re-listing")


def _closed_signal(posting: Posting) -> Signal | None:
    if posting.is_active:
        return None
    return Signal("Source status", Verdict.CONCERN, "A source has marked this role closed")


def _description_signal(posting: Posting) -> Signal:
    """Not evidence of ghosting, but it governs how much the match score is
    worth, so it belongs on the same panel."""
    if posting.description_available:
        return Signal("Description", Verdict.GOOD, "Full description available")
    return Signal(
        "Description",
        Verdict.NEUTRAL,
        "Title only; match scoring for this role is weaker evidence",
    )


def _label_from(signals: list[Signal], age_days: int | None) -> GhostLabel:
    """Derive the headline from the signals.

    Kept simple and readable on purpose: the operator can reconstruct it from
    the checklist, which is the point.
    """
    concerns = sum(1 for s in signals if s.verdict is Verdict.CONCERN)
    unknowns = sum(1 for s in signals if s.verdict is Verdict.UNKNOWN)

    if age_days is None and unknowns >= 3:
        return GhostLabel.INSUFFICIENT_DATA
    if concerns == 0:
        return GhostLabel.LIKELY_ACTIVE
    if concerns == 1:
        return GhostLabel.PROBABLY_FINE
    if concerns == 2:
        return GhostLabel.QUESTIONABLE
    return GhostLabel.LIKELY_STALE


def assess(posting: Posting, *, source_count: int, today: date | None = None) -> GhostAssessment:
    """Build the signal checklist for one posting."""
    today = today or datetime.now(UTC).date()
    age_days = (
        None
        if posting.posted_at is None
        else max(0, (today - posting.posted_at.astimezone(UTC).date()).days)
    )

    signals = [
        _age_signal(age_days),
        _freshness_signal(posting, today),
        _refresh_signal(posting),
        _corroboration_signal(source_count),
        _description_signal(posting),
    ]
    if (closed := _closed_signal(posting)) is not None:
        signals.insert(0, closed)

    return GhostAssessment(label=_label_from(signals, age_days), signals=signals)
