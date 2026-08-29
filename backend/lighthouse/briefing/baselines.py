"""Published funnel baselines, and why this file ships empty.

The spec asks for the operator's own funnel to be shown against published
industry figures, so a quiet fortnight reads as "normal for this stage" rather
than as a verdict. That is a genuinely useful feature and it is the single
easiest place in this project to fabricate.

So there are no numbers here. Not because the feature was skipped, but because
a plausible-looking "published baseline: 5-12%" that nobody can trace is exactly
the invented number this project refuses to print -- and it would be *worse*
than no baseline, because the operator would calibrate real decisions against
it.

The mechanism is built. To turn it on, add entries below with a real source and
the date it was retrieved. Candidates the plan identified:

* **NACE** (naceweb.org) publishes annual internship conversion and offer rates.
* **Greenhouse** and **Ashby** publish aggregate hiring-funnel reports.
* **Handshake** publishes student-side application volume data.

Each entry states the population it was measured over, because "8% is normal"
is meaningless without knowing normal for whom.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Baseline:
    """One published figure, with everything needed to check it."""

    stage_from: str
    stage_to: str
    low_pct: int
    high_pct: int
    population: str
    source: str
    source_url: str
    retrieved: date

    @property
    def label(self) -> str:
        return f"{self.stage_from} → {self.stage_to}"

    def statement(self) -> str:
        return (
            f"Published range {self.low_pct}–{self.high_pct}% for {self.population} "
            f"({self.source}, retrieved {self.retrieved.isoformat()})."
        )


# Deliberately empty. See the module docstring before adding anything.
BASELINES: tuple[Baseline, ...] = ()


def for_conversion(stage_from: str, stage_to: str) -> Baseline | None:
    """The published range for one transition, if one has been loaded."""
    return next(
        (
            b
            for b in BASELINES
            if b.stage_from.lower() == stage_from.lower()
            and b.stage_to.lower() == stage_to.lower()
        ),
        None,
    )


def note() -> str:
    """What to tell the operator about the comparison they are not getting."""
    if BASELINES:
        return f"{len(BASELINES)} published baselines loaded."
    return (
        "No published baselines are loaded, so your rates are shown on their own. "
        "Lighthouse will not print a comparison figure it cannot cite — an "
        "uncheckable 'industry average' is worse than none, because you would "
        "plan against it."
    )
