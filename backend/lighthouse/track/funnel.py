"""Funnel counts over folded application states.

Conversions are measured from Applied and shown with both numbers; below
``MIN_SAMPLE`` no percentage is given at all. Wait times are observed medians
with their sample size, never a fitted distribution.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date

from .applications import OPERATOR_EVENTS, STAGE_LABELS, ApplicationState, Stage

# Below this many applications reaching a stage, no conversion figure is
# reported. It is a judgement call, stated in one place, and it is deliberately
# not a confidence interval — that would be the same false precision by another
# route.
MIN_SAMPLE = 10


@dataclass(slots=True)
class StageCount:
    stage: Stage
    label: str
    # Applications that reached this stage at any point, including ones that
    # have since moved past it or been rejected out of it.
    reached: int
    # Applications sitting here right now.
    current: int


@dataclass(slots=True)
class Conversion:
    """Movement between two stages, with both numbers shown."""

    from_label: str
    to_label: str
    reached_from: int
    reached_to: int

    @property
    def has_enough_data(self) -> bool:
        return self.reached_from >= MIN_SAMPLE

    @property
    def statement(self) -> str:
        if not self.has_enough_data:
            return f"{self.reached_to} of {self.reached_from} — too few to read anything into yet"
        pct = round(100 * self.reached_to / self.reached_from)
        return f"{self.reached_to} of {self.reached_from} ({pct}%)"


@dataclass(slots=True)
class WaitTime:
    """Observed gap between two stages. A median of real waits, with n."""

    from_label: str
    to_label: str
    days: list[int] = field(default_factory=list)

    @property
    def sample_size(self) -> int:
        return len(self.days)

    @property
    def median_days(self) -> int | None:
        return round(statistics.median(self.days)) if self.days else None

    @property
    def statement(self) -> str:
        if not self.days:
            return "no observations yet"
        median = self.median_days
        if self.sample_size < 3:
            observed = ", ".join(f"{d}d" for d in sorted(self.days))
            return f"observed: {observed} (n={self.sample_size})"
        return (
            f"median {median} days (n={self.sample_size}, range {min(self.days)}–{max(self.days)})"
        )


@dataclass(slots=True)
class FunnelReport:
    total: int
    stages: list[StageCount] = field(default_factory=list)
    conversions: list[Conversion] = field(default_factory=list)
    waits: list[WaitTime] = field(default_factory=list)
    # Live applications with no employer response, longest wait first. Dated
    # facts, not predictions of ghosting.
    silent: list[tuple[str, int]] = field(default_factory=list)

    @property
    def has_enough_data(self) -> bool:
        return self.total >= MIN_SAMPLE

    def basis(self) -> str:
        if self.total == 0:
            return "No applications logged yet."
        if not self.has_enough_data:
            return (
                f"{self.total} application{'s' if self.total != 1 else ''} so far. "
                "Counts are real; rates are not shown until there are enough to mean something."
            )
        return f"Across {self.total} logged applications."


# The stages a board displays, in order.
FUNNEL_PATH: tuple[Stage, ...] = (
    Stage.APPLIED,
    Stage.ASSESSMENT,
    Stage.INTERVIEW,
    Stage.FINAL,
    Stage.OFFER,
)


def logged_at(state: ApplicationState, stage: Stage) -> bool:
    """Whether an event was logged at exactly this stage.

    Stage counts use this rather than "at least this far": many roles have no
    online assessment, and an application that went applied -> interview never
    reached one.
    """
    return any(entry.stage == stage for entry in state.timeline)


def progressed_to(state: ApplicationState, stage: Stage) -> bool:
    """Whether this application got at least this far.

    Terminal entries are excluded so a rejection, which sorts above every live
    stage, does not count as progress.
    """
    return any(entry.stage >= stage and not entry.stage.is_terminal for entry in state.timeline)


def _first_at(state: ApplicationState, stage: Stage):
    return next((e.occurred_at for e in state.timeline if e.stage == stage), None)


def _first_response(state: ApplicationState):
    """When the employer first said anything. A rejection counts: it is the most
    common reply, and often the only one."""
    return next(
        (
            e.occurred_at
            for e in state.timeline
            if e.stage > Stage.APPLIED and e.event_type not in OPERATOR_EVENTS
        ),
        None,
    )


def build(states: list[ApplicationState], *, today: date | None = None) -> FunnelReport:
    """Compute the funnel from folded application states.

    Counts only applications actually sent; a saved bookmark is not an
    application. Conversions are measured from Applied rather than between
    consecutive stages, since not every application passes through every stage.
    """
    states = [s for s in states if progressed_to(s, Stage.APPLIED)]
    report = FunnelReport(total=len(states))
    if not states:
        return report

    for stage in (*FUNNEL_PATH, Stage.REJECTED):
        report.stages.append(
            StageCount(
                stage=stage,
                label=STAGE_LABELS[stage],
                reached=sum(1 for s in states if logged_at(s, stage)),
                current=sum(1 for s in states if s.stage == stage),
            )
        )

    applied = sum(1 for s in states if progressed_to(s, Stage.APPLIED))
    for stage, label in (
        (Stage.ASSESSMENT, "heard anything back"),
        (Stage.INTERVIEW, "reached an interview"),
        (Stage.OFFER, "reached an offer"),
    ):
        report.conversions.append(
            Conversion(
                from_label="Applied",
                to_label=label,
                reached_from=applied,
                reached_to=sum(1 for s in states if progressed_to(s, stage)),
            )
        )

    # Gaps worth knowing, each between two dates that actually exist on the
    # record. Company Intelligence will later compare these to what other
    # people report for the same company.
    for label, start_of, end_of in (
        ("first response", lambda s: _first_at(s, Stage.APPLIED), _first_response),
        (
            "an interview",
            lambda s: _first_at(s, Stage.APPLIED),
            lambda s: _first_at(s, Stage.INTERVIEW),
        ),
        (
            "an offer",
            lambda s: _first_at(s, Stage.INTERVIEW),
            lambda s: _first_at(s, Stage.OFFER),
        ),
    ):
        gaps: list[int] = []
        for state in states:
            start, end = start_of(state), end_of(state)
            if start and end and end >= start:
                gaps.append((end.date() - start.date()).days)
        report.waits.append(
            WaitTime(
                from_label="Applied" if "offer" not in label else "Interview",
                to_label=label,
                days=gaps,
            )
        )

    report.silent = sorted(
        (
            (label, days)
            for label, days in ((str(s.application_id), s.days_silent(today)) for s in states)
            if days is not None
        ),
        key=lambda row: -row[1],
    )
    return report
