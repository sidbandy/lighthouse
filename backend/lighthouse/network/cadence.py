"""When to follow up, and when to stop.

The mechanically boring feature that produces most of the value. Threads die
from a missed follow-up far more often than from a bad first message, and
remembering fifteen of them is not something a person should be doing in their
head.

Two rules keep this from becoming a nag, and both are deliberate.

**Two follow-ups, then stop.** A third message does not get answered; it gets
you remembered for the wrong reason. Once the sequence is exhausted the engine
says so and produces nothing further, rather than accruing a guilt counter --
the same lesson the study scheduler will need, learned here first.

**Nothing is ever sent.** Every output is a due date and a draft the operator
opens, edits and sends themselves. Automated outbound to real people is a
reputation risk with no upside for a single person running one search.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .contacts import ContactState, Kind, Stage

# The default cadences. Days, from the anchoring event.
#
# Cold outreach is spaced wider than instinct suggests on purpose: a chase two
# days after the first message reads as pressure, and a week reads as diligence.
COLD_FIRST_FOLLOWUP_DAYS = 7
COLD_SECOND_FOLLOWUP_DAYS = 14
MAX_UNANSWERED_MESSAGES = 3  # the opener plus two follow-ups

# After a real conversation, a thank-you is same-or-next-day and an update is a
# few weeks out. Beyond that a relationship is maintained, not worked.
THANK_YOU_DAYS = 1
POST_CONVERSATION_UPDATE_DAYS = 24
QUARTERLY_TOUCH_DAYS = 90


@dataclass(slots=True)
class NextStep:
    """One thing worth doing, on a real date.

    ``due_on`` is a date the operator can check against a calendar, not a
    priority score. ``reason`` says which fact produced it, so a step that looks
    wrong can be traced rather than argued with.
    """

    action: str
    due_on: date
    reason: str
    # What a draft for this step should be built around. Lets the drafting layer
    # pick a register without re-deriving the situation.
    draft_kind: str

    def days_until(self, today: date | None = None) -> int:
        return (self.due_on - (today or datetime.now(UTC).date())).days

    def is_due(self, today: date | None = None) -> bool:
        return self.days_until(today) <= 0

    def status(self, today: date | None = None) -> str:
        days = self.days_until(today)
        if days > 1:
            return f"in {days} days"
        if days == 1:
            return "tomorrow"
        if days == 0:
            return "today"
        overdue = -days
        return f"{overdue} day{'s' if overdue != 1 else ''} late"


@dataclass(slots=True)
class Cadence:
    """What to do next with one contact, or why there is nothing to do."""

    next_step: NextStep | None
    note: str

    @property
    def has_step(self) -> bool:
        return self.next_step is not None


def _d(moment: datetime) -> date:
    return moment.astimezone(UTC).date()


def next_step_for(state: ContactState, *, today: date | None = None) -> Cadence:
    """The single next thing worth doing with this contact.

    One step, not a list. A queue of five things per person is a queue nobody
    works; the next action is the only one that can actually be taken now.
    """
    today = today or datetime.now(UTC).date()

    if not state.timeline:
        return Cadence(
            next_step=NextStep(
                action="Send the first message",
                due_on=today,
                reason="Nothing sent yet.",
                draft_kind="cold_outreach",
            ),
            note="",
        )

    if state.referral_confirmed:
        return Cadence(
            next_step=None,
            note="They referred you. Worth a thank-you and an update when you hear back.",
        )

    # A conversation happened: the follow-up is warm and specific, and the
    # sequence is not the cold one.
    spoke_at = state.spoke_at
    if spoke_at is not None:
        thanked = any(
            e.kind is Kind.THANK_YOU and e.occurred_at >= spoke_at for e in state.timeline
        )
        if not thanked:
            return Cadence(
                next_step=NextStep(
                    action="Send a thank-you",
                    due_on=_d(spoke_at) + timedelta(days=THANK_YOU_DAYS),
                    reason=f"You spoke on {_d(spoke_at).isoformat()}.",
                    draft_kind="thank_you",
                ),
                note="",
            )
        last = state.last_interaction_at
        anchor = _d(last) if last else _d(spoke_at)
        gap = (today - anchor).days
        interval = (
            POST_CONVERSATION_UPDATE_DAYS if gap < QUARTERLY_TOUCH_DAYS else QUARTERLY_TOUCH_DAYS
        )
        return Cadence(
            next_step=NextStep(
                action="Send an update",
                due_on=anchor + timedelta(days=interval),
                reason=f"Last contact {anchor.isoformat()}. Keep a warm thread warm.",
                draft_kind="update",
            ),
            note="",
        )

    # They replied and the ball is with you.
    if state.stage is Stage.IN_CONVERSATION:
        return Cadence(
            next_step=NextStep(
                action="Reply",
                due_on=today,
                reason="They wrote back and are waiting on you.",
                draft_kind="reply",
            ),
            note="",
        )

    # Cold, unanswered. This is where the limit applies.
    sent = state.last_outbound_at
    if sent is None:
        return Cadence(
            next_step=NextStep(
                action="Send the first message",
                due_on=today,
                reason="Nothing has gone out yet.",
                draft_kind="cold_outreach",
            ),
            note="",
        )

    attempts = state.unanswered_outreach
    if attempts >= MAX_UNANSWERED_MESSAGES:
        return Cadence(
            next_step=None,
            note=(
                f"{attempts} messages, no reply. That is the limit — a third follow-up "
                "does not get answered. Leave it; if you meet them somewhere, start again."
            ),
        )

    wait = COLD_FIRST_FOLLOWUP_DAYS if attempts <= 1 else COLD_SECOND_FOLLOWUP_DAYS
    ordinal = "first" if attempts <= 1 else "second"
    return Cadence(
        next_step=NextStep(
            action=f"Send the {ordinal} follow-up",
            due_on=_d(sent) + timedelta(days=wait),
            reason=(
                f"You wrote on {_d(sent).isoformat()} and have not heard back. "
                f"{MAX_UNANSWERED_MESSAGES - attempts} left before this one is done."
            ),
            draft_kind="follow_up",
        ),
        note="",
    )


@dataclass(slots=True)
class QueueItem:
    contact_id: str
    name: str
    company_name: str | None
    step: NextStep


def due_queue(
    rows: list[tuple], *, today: date | None = None, horizon_days: int = 0
) -> list[QueueItem]:
    """Everything due now, most overdue first.

    ``rows`` is ``(contact, state)`` pairs. ``horizon_days`` looks ahead, which
    is how the weekly briefing will ask "what is coming this week" without
    changing what counts as due today.
    """
    today = today or datetime.now(UTC).date()
    items: list[QueueItem] = []
    for contact, state in rows:
        cadence = next_step_for(state, today=today)
        if cadence.next_step is None:
            continue
        if cadence.next_step.days_until(today) > horizon_days:
            continue
        items.append(
            QueueItem(
                contact_id=str(contact.id),
                name=contact.name,
                company_name=contact.company_name,
                step=cadence.next_step,
            )
        )
    items.sort(key=lambda i: i.step.due_on)
    return items
