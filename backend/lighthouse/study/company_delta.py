"""What a specific company actually asks, crossed with the operator's record.

This is the sentence the whole product is arranged around:

    Citadel's last 6 months of reported OAs: 8 of 20 tagged graph traversal.
    Your graph attempts: 2 of 7 clean. Highest-leverage practice this week.

Observed counts on both sides, and it needs both. Without the company half it is
a generic weak-spot list; without the operator half it is a company trivia page.

**`reported_questions` is empty today.** Populating it is Company Intelligence's
job -- Reddit and LeetCode through the review queue -- and until that lands this
module reports having no data rather than inventing a distribution. An honest
"no reports for this company" is worth more than a confident-looking pie chart
built from nothing, because the second one gets acted on.

Recency weighting is here rather than in a shared helper for now, but it is the
same exponential the interview-report aggregation will need, and it should move
when the second caller exists.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import Company, ReportedQuestion
from .attempts import PatternRecord, records
from .catalog import PATTERNS_BY_SLUG

# A report from a year ago counts about a third of one from this month.
# Companies rotate their question pools; a 2023 report is history, not signal.
HALF_LIFE_MONTHS = 12.0

# Below this many reports, no distribution is shown at all. A "40% graphs" built
# from two posts is a number someone will plan a week around.
MIN_REPORTS = 5


def recency_weight(reported: date | None, *, today: date | None = None) -> float:
    """Exponential decay by age. Undated reports count, but least."""
    if reported is None:
        return 0.25
    today = today or datetime.now(UTC).date()
    months = max(0.0, (today - reported).days / 30.44)
    return math.exp(-months / HALF_LIFE_MONTHS)


@dataclass(slots=True)
class PatternDemand:
    """One pattern, and how much of a company's reported questions it accounts for."""

    slug: str
    name: str
    report_count: int
    weighted: float
    share: float  # of the weighted total, 0-1

    @property
    def percent(self) -> int:
        return round(self.share * 100)


@dataclass(slots=True)
class CompanyDelta:
    """A company's reported pattern mix against the operator's own record."""

    company_name: str
    report_count: int
    newest_report: date | None = None
    oldest_report: date | None = None
    demand: list[PatternDemand] = field(default_factory=list)
    # Where their emphasis meets a pattern the operator is weak on.
    leverage: list[tuple[PatternDemand, PatternRecord]] = field(default_factory=list)

    @property
    def coverage_quality(self) -> str:
        """rich | partial | none. Rendered everywhere the data appears, because
        a confident-looking empty record is worse than an honest gap."""
        if self.report_count == 0:
            return "none"
        return "rich" if self.report_count >= MIN_REPORTS * 3 else "partial"

    def note(self) -> str:
        if self.report_count == 0:
            return (
                f"No interview reports for {self.company_name} yet. Company Intelligence "
                "populates this from public reports; until then, work the core patterns — "
                "they are what everyone asks regardless."
            )
        if self.report_count < MIN_REPORTS:
            span = ""
            if self.newest_report:
                span = f" (newest {self.newest_report.isoformat()})"
            return (
                f"Only {self.report_count} report{'s' if self.report_count != 1 else ''} "
                f"for {self.company_name}{span} — too few to call it a pattern mix."
            )
        newest = self.newest_report.isoformat() if self.newest_report else "unknown"
        return (
            f"{self.report_count} reports for {self.company_name}, newest {newest}, "
            "weighted toward recent ones."
        )

    def leverage_statements(self) -> list[str]:
        """The connection sentence, with counts on both sides."""
        lines = []
        for demand, record in self.leverage:
            lines.append(
                f"{self.company_name}: {demand.report_count} of {self.report_count} reported "
                f"questions tagged {demand.name.lower()}. "
                f"Your record: {record.clean} of {record.total} clean."
            )
        return lines


def _operator_id() -> uuid.UUID:
    from ..core.config import get_settings

    return get_settings().operator_id


def build(
    session: Session,
    company_id: uuid.UUID,
    *,
    today: date | None = None,
    user_id: uuid.UUID | None = None,
) -> CompanyDelta:
    """One company's reported pattern mix, crossed with the operator's record."""
    company = session.get(Company, company_id)
    name = company.name if company else "This company"

    reports = list(
        session.scalars(
            select(ReportedQuestion).where(ReportedQuestion.company_id == company_id)
        )
    )
    dates = [r.reported_date for r in reports if r.reported_date]
    delta = CompanyDelta(
        company_name=name,
        report_count=len(reports),
        newest_report=max(dates) if dates else None,
        oldest_report=min(dates) if dates else None,
    )
    if len(reports) < MIN_REPORTS:
        return delta

    weighted: defaultdict[str, float] = defaultdict(float)
    counts: defaultdict[str, int] = defaultdict(int)
    for report in reports:
        weight = recency_weight(report.reported_date, today=today)
        for tag in report.pattern_tags or []:
            if tag in PATTERNS_BY_SLUG:
                weighted[tag] += weight
                counts[tag] += 1

    total = sum(weighted.values())
    if total <= 0:
        return delta

    delta.demand = sorted(
        (
            PatternDemand(
                slug=slug,
                name=PATTERNS_BY_SLUG[slug].name,
                report_count=counts[slug],
                weighted=round(value, 3),
                share=value / total,
            )
            for slug, value in weighted.items()
        ),
        key=lambda d: -d.weighted,
    )

    by_slug = {r.slug: r for r in records(session, user_id=user_id)}
    delta.leverage = [
        (demand, record)
        for demand in delta.demand[:6]
        if (record := by_slug.get(demand.slug)) is not None
        and (record.is_weak or record.is_untouched)
    ]
    return delta
