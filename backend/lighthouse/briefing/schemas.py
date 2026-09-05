"""Wire shapes for the weekly briefing.

Thin mirrors of the dataclasses in :mod:`weekly`. The briefing assembles rather
than computes, and these carry that through: every item keeps the reason and
the date that produced it, and an empty section keeps its note saying which
kind of empty it is. Nothing here is a score.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class BriefItemOut(BaseModel):
    kind: str = Field(description="outreach | stale | review | weak_pattern | story_gap | reliance")
    title: str
    detail: str = Field(description="The fact that produced this item, in words.")
    link: str = Field(description="Where to go and do it.")
    due_on: date | None = Field(
        default=None, description="A real date, when the item has one. Never a priority score."
    )
    is_late: bool = False


class BriefSectionOut(BaseModel):
    key: str
    title: str
    items: list[BriefItemOut] = Field(default_factory=list)
    count: int
    empty_note: str = Field(
        default="",
        description=(
            "Shown instead of the items when there are none. An empty section is "
            "information, but only if it says which kind of empty it is."
        ),
    )


class WeeklyBriefOut(BaseModel):
    generated_for: date
    headline: str
    total_items: int
    late_items: int
    sections: list[BriefSectionOut] = Field(default_factory=list)
    funnel_note: str = Field(
        default="",
        description="How the funnel rates were derived, or why they are withheld.",
    )
    baseline_note: str = Field(
        default="",
        description="What comparison is not being shown, and why it is not invented.",
    )


class TriageOut(BaseModel):
    application_id: UUID
    posting_title: str
    company_name: str
    band: str = Field(description="deep | standard | light")
    band_blurb: str
    reason: str = Field(description="Why this application landed in this band.")
    stage_label: str


class TriageGroupOut(BaseModel):
    """One effort band and the applications in it."""

    band: str
    blurb: str
    applications: list[TriageOut] = Field(default_factory=list)
    count: int
