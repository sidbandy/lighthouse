"""The weekly briefing: everything due, in one place, once a week.

The point is not to add another surface. It is to stop the operator holding the
whole season in their head, which is where most of the stress in a job search
actually lives — not in any single rejection but in the constant background
sense that something is being missed.

So this assembles rather than computes. Every line already exists somewhere:
follow-ups from the cadence engine, silent applications from the board, weak
patterns and due reviews from Study, uncovered competencies from the story bank.
The briefing's only job is to put them on one page in the order they should be
worked, and to say plainly when a section is empty rather than padding it.

Nothing here is scored, ranked by a model, or predicted. Every item is a dated
fact with the reason attached.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from ..core import corpus as corpus_service
from ..network import cadence
from ..network import contacts as contacts_service
from ..study import attempts as study_attempts
from ..study import srs
from ..track import applications as track
from ..track import funnel as funnel_service
from . import baselines

# An application with no employer signal for this long is worth a nudge. Not a
# verdict on it -- rolling review genuinely takes weeks -- but long enough that
# forgetting is the more likely explanation than silence.
STALE_AFTER_DAYS = 14

# How far ahead "this week" looks.
HORIZON_DAYS = 7


@dataclass(slots=True)
class BriefItem:
    """One thing worth doing, with the fact that produced it."""

    kind: str
    title: str
    detail: str
    # Where to go and do it.
    link: str
    # Real date when the item has one. Never a priority score.
    due_on: date | None = None
    is_late: bool = False


@dataclass(slots=True)
class BriefSection:
    key: str
    title: str
    items: list[BriefItem] = field(default_factory=list)
    # What to say when there is nothing. An empty section is information too,
    # but only if it says which kind of empty it is.
    empty_note: str = ""

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(slots=True)
class WeeklyBrief:
    generated_for: date
    sections: list[BriefSection] = field(default_factory=list)
    funnel_note: str = ""
    baseline_note: str = ""

    @property
    def total_items(self) -> int:
        return sum(s.count for s in self.sections)

    def headline(self) -> str:
        if self.total_items == 0:
            return (
                "Nothing is due. Either you are on top of it or there is not enough "
                "in Lighthouse yet for it to tell you otherwise."
            )
        late = sum(1 for s in self.sections for i in s.items if i.is_late)
        if late:
            return f"{self.total_items} things this week, {late} already past their date."
        return f"{self.total_items} things this week."


def _operator_id() -> uuid.UUID:
    from ..core.config import get_settings

    return get_settings().operator_id


def build(
    session: Session, *, today: date | None = None, user_id: uuid.UUID | None = None
) -> WeeklyBrief:
    """Assemble the week. Reads every module; computes nothing new."""
    today = today or datetime.now(UTC).date()
    uid = user_id or _operator_id()
    brief = WeeklyBrief(generated_for=today)

    # 1. Outreach that is due. Threads die from a missed follow-up more often
    #    than from a bad first message.
    rows = contacts_service.list_contacts(session, user_id=uid)
    queue = cadence.due_queue(rows, today=today, horizon_days=HORIZON_DAYS)
    brief.sections.append(
        BriefSection(
            key="outreach",
            title="People to write to",
            items=[
                BriefItem(
                    kind="outreach",
                    title=q.name + (f" · {q.company_name}" if q.company_name else ""),
                    detail=f"{q.step.action} — {q.step.reason}",
                    link="/network",
                    due_on=q.step.due_on,
                    is_late=q.step.days_until(today) < 0,
                )
                for q in queue
            ],
            empty_note=(
                "Nothing due. Every thread is either waiting on them or finished."
                if rows
                else "No contacts yet. One afternoon on your school's alumni page changes that."
            ),
        )
    )

    # 2. Applications that have gone quiet. A dated fact, not a probability.
    board = track.board(session, user_id=uid)
    stale = [
        (state, posting)
        for state, posting in board
        if (state.days_silent(today) or 0) >= STALE_AFTER_DAYS
    ]
    brief.sections.append(
        BriefSection(
            key="stale",
            title="Applications that have gone quiet",
            items=[
                BriefItem(
                    kind="stale",
                    title=f"{posting.title} · {posting.company.name if posting.company else '—'}",
                    detail=state.silence_note(today) or "",
                    link="/applications",
                    due_on=None,
                    is_late=(state.days_silent(today) or 0) >= STALE_AFTER_DAYS * 2,
                )
                for state, posting in stale
            ],
            empty_note=(
                "Nothing has been silent longer than two weeks."
                if board
                else "Nothing tracked yet. Save a posting from Discover and it appears here."
            ),
        )
    )

    # 3. Study: what is due, and the pattern most worth an hour.
    reviews = srs.build_queue(session, today=today, user_id=uid)
    records = study_attempts.records(session, user_id=uid)
    weak = [r for r in records if r.is_weak][:2]
    study_items = [
        BriefItem(
            kind="review",
            title=f"{len(reviews.due)} problems due for review",
            detail=reviews.note(),
            link="/study",
            due_on=today,
        )
    ] if reviews.due else []
    study_items += [
        BriefItem(
            kind="weak_pattern",
            title=f"Practise {r.pattern.name.lower()}",
            detail=r.statement(today),
            link="/study",
        )
        for r in weak
    ]
    brief.sections.append(
        BriefSection(
            key="study",
            title="Study this week",
            items=study_items,
            empty_note=(
                "Nothing due, and no pattern has enough attempts logged to call weak yet."
            ),
        )
    )

    # 4. Behavioural gaps. A competency with no story is a finite, fixable hole.
    coverage = corpus_service.story_coverage(session, user_id=uid)
    # With no stories at all, every competency is "uncovered" -- so listing
    # three of the nine would be picking arbitrary ones and calling them this
    # week's work, and the headline would announce three things to an operator
    # who has put nothing in yet. The note below is the honest first message,
    # and gaps become real gaps once there is a bank to have gaps in.
    uncovered = coverage.uncovered[:3] if coverage.story_count else []
    brief.sections.append(
        BriefSection(
            key="stories",
            title="Stories to write",
            items=[
                BriefItem(
                    kind="story_gap",
                    title=f"No story for {c.slug}",
                    detail=c.prompt,
                    link="/corpus",
                )
                for c in uncovered
            ],
            empty_note=(
                "Every competency has a story behind it."
                if coverage.story_count
                else "No stories yet. They are what a behavioural round actually runs on."
            ),
        )
    )

    # 5. Over-relied-on projects, when there are enough stories to tell.
    if coverage.reliance:
        brief.sections.append(
            BriefSection(
                key="reliance",
                title="Worth spreading out",
                items=[
                    BriefItem(
                        kind="reliance",
                        title=(
                            f"{r.story_count} of {coverage.story_count} stories "
                            f"use {r.fact_title}"
                        ),
                        detail="An interviewer hearing the same project four times notices.",
                        link="/corpus",
                    )
                    for r in coverage.reliance
                ],
            )
        )

    states = [state for state, _ in board]
    if states:
        report = funnel_service.build(states)
        brief.funnel_note = report.basis()
    brief.baseline_note = baselines.note()
    return brief


@dataclass(slots=True)
class Triage:
    """One live application and how much preparation it is worth.

    Not every application deserves equal effort, and pretending otherwise is
    what makes everything feel equally urgent. The placement rule is legible and
    the reason travels with it, so the operator can disagree with a specific
    call rather than with a number.
    """

    application_id: uuid.UUID
    posting_title: str
    company_name: str
    band: str  # deep | standard | light
    reason: str
    stage_label: str


# Bands, in the order they are worked.
BANDS = ("deep", "standard", "light")

BAND_BLURB: dict[str, str] = {
    "deep": "Worth company-specific study and a tailored résumé pass.",
    "standard": "Apply well, prepare with the core patterns.",
    "light": "Send it and move on.",
}


def triage(
    session: Session, *, today: date | None = None, user_id: uuid.UUID | None = None
) -> list[Triage]:
    """Sort live applications into deep / standard / light.

    Placement is driven by how far the application has actually got, because
    that is the fact that most changes what preparation is worth: an interview
    next week earns real study, and something sent yesterday earns none yet.
    """
    today = today or datetime.now(UTC).date()
    uid = user_id or _operator_id()
    out: list[Triage] = []

    for state, posting in track.board(session, user_id=uid):
        if not state.stage.is_live:
            continue
        stage = state.stage
        if stage >= track.Stage.INTERVIEW:
            band, reason = "deep", "You are interviewing. This is where preparation pays."
        elif stage is track.Stage.ASSESSMENT:
            band, reason = "deep", "An assessment is in play — practise the patterns now."
        elif stage is track.Stage.APPLIED:
            silent = state.days_silent(today) or 0
            if silent >= STALE_AFTER_DAYS:
                band, reason = "light", (
                    f"Sent {silent} days ago with no reply. "
                    "Do not spend more on it yet."
                )
            else:
                band, reason = "standard", "Sent recently. Core preparation covers it."
        else:
            # Unreachable: the only remaining stages are SAVED and the terminal
            # ones, and `is_live` filtered both out above. Kept as a loud
            # failure rather than a silent default, because a new stage added
            # to the enum should stop here and be given a band deliberately.
            raise AssertionError(f"no triage band for live stage {stage!r}")

        out.append(
            Triage(
                application_id=state.application_id,
                posting_title=posting.title,
                company_name=posting.company.name if posting.company else "—",
                band=band,
                reason=reason,
                stage_label=track.STAGE_LABELS[stage],
            )
        )

    out.sort(key=lambda t: BANDS.index(t.band))
    return out
