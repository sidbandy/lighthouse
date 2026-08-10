"""Referred applications against cold ones.

A referral is not a property of an application; it is something that happened,
on a date, between the operator and a person. So it lives in the interaction log
with the application it was about, and "was this referred" is folded from that
the same way every other state in this project is.

The counts stay counts. Everyone believes referrals convert better, and they
probably do, but a student with nine applications and one referral has not
measured that -- and a percentage on those numbers moves twenty points on a
single reply. What the operator gets is the two figures side by side and the
sample sizes attached, which is enough to see a real difference when there is
one and not enough to fool themselves when there is not.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import ContactInteraction
from ..track.applications import OPERATOR_EVENTS, ApplicationState
from .contacts import Kind

# Below this, the two groups are not worth putting beside each other at all:
# "1 of 1 referred applications got a response" is a sentence that teaches
# nothing and reads like evidence.
MIN_PER_GROUP = 3


@dataclass(slots=True)
class RouteOutcome:
    """One route into a company, and what happened to it."""

    route: str
    applied: int
    responded: int

    @property
    def statement(self) -> str:
        if self.applied == 0:
            return f"no {self.route} applications yet"
        return f"{self.responded} of {self.applied} got a response"


@dataclass(slots=True)
class ReferralReport:
    referred: RouteOutcome
    cold: RouteOutcome

    @property
    def is_comparable(self) -> bool:
        return self.referred.applied >= MIN_PER_GROUP and self.cold.applied >= MIN_PER_GROUP

    def note(self) -> str:
        if self.referred.applied == 0:
            return (
                "No referred applications yet. Asking someone already inside is the "
                "single highest-leverage thing on this page."
            )
        if not self.is_comparable:
            return (
                f"Referred: {self.referred.statement}. Cold: {self.cold.statement}. "
                f"Too few either side to compare — {MIN_PER_GROUP} of each is the floor."
            )
        return f"Referred: {self.referred.statement}. Cold: {self.cold.statement}."


def referred_application_ids(
    session: Session, *, user_id: uuid.UUID | None = None
) -> set[uuid.UUID]:
    """Applications with a confirmed referral behind them.

    Asking is not being referred. Only ``referral_confirmed`` counts, because an
    unanswered ask is exactly the cold case wearing a hopeful label, and letting
    it through would flatter the referred column with the applications that went
    worst.
    """
    from ..core.config import get_settings

    uid = user_id or get_settings().operator_id
    rows = session.scalars(
        select(ContactInteraction.application_id).where(
            ContactInteraction.user_id == uid,
            ContactInteraction.kind == Kind.REFERRAL_CONFIRMED.value,
            ContactInteraction.application_id.isnot(None),
        )
    )
    return {rid for rid in rows if rid is not None}


def build(
    states: list[ApplicationState], referred_ids: set[uuid.UUID]
) -> ReferralReport:
    """Split folded application states by how the operator got in."""
    groups = {"referred": [0, 0], "cold": [0, 0]}
    for state in states:
        if state.applied_at is None:
            continue
        key = "referred" if state.application_id in referred_ids else "cold"
        groups[key][0] += 1
        if any(e.event_type not in OPERATOR_EVENTS for e in state.timeline):
            groups[key][1] += 1

    return ReferralReport(
        referred=RouteOutcome("referred", *groups["referred"]),
        cold=RouteOutcome("cold", *groups["cold"]),
    )
