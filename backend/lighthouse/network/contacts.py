"""Contacts, and their state folded from the interaction log.

Same shape as the application board, for the same reason: a mutable "status"
column would answer none of the three questions this module exists for -- when
did I last write, how long have they been quiet, and how many times have I
already asked. Those are all subtractions between real dates, so the dates are
what get stored.

The bottleneck in networking was never finding names. It is writing fifteen
non-generic messages and remembering to follow up on all of them, and the second
half is bookkeeping that a person should not be doing in their head.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.models import Company, Contact, ContactInteraction
from ..ingest.normalize import canonical_company


class Relationship(StrEnum):
    COLD = "cold"
    WARM_INTRO = "warm_intro"
    ALUMNI = "alumni"
    MET_AT_EVENT = "met_at_event"
    REFERRED_BY = "referred_by"


class Kind(StrEnum):
    """What actually happened. Kept small: every value here has to change either
    what the follow-up engine does next or what a draft can reference."""

    OUTREACH = "outreach"
    REPLY = "reply"
    CONVERSATION = "conversation"
    REFERRAL_ASKED = "referral_asked"
    REFERRAL_CONFIRMED = "referral_confirmed"
    THANK_YOU = "thank_you"
    NOTE = "note"


KIND_LABELS: dict[Kind, str] = {
    Kind.OUTREACH: "Reached out",
    Kind.REPLY: "They replied",
    Kind.CONVERSATION: "Spoke",
    Kind.REFERRAL_ASKED: "Asked for a referral",
    Kind.REFERRAL_CONFIRMED: "Referral confirmed",
    Kind.THANK_YOU: "Thank you sent",
    Kind.NOTE: "Note",
}

# Anything the operator does themselves. Silence runs from the last of these,
# so adding a note to a thread that has gone quiet must not make it look alive
# -- the same rule the application board follows, and for the same reason.
OPERATOR_KINDS = frozenset(
    {Kind.OUTREACH, Kind.REFERRAL_ASKED, Kind.THANK_YOU, Kind.NOTE}
)

# Messages that actually put the ball in their court. A thank-you does not: it
# closes a loop rather than opening one, and counting it as an unanswered
# message would mark every warm relationship "awaiting reply" forever and
# print "6 days since you wrote, no reply" under a thread that is going fine.
AWAITING_KINDS = frozenset({Kind.OUTREACH, Kind.REFERRAL_ASKED})


class Stage(StrEnum):
    """Where a relationship actually is. Derived, never stored."""

    NOT_CONTACTED = "not_contacted"
    AWAITING_REPLY = "awaiting_reply"
    IN_CONVERSATION = "in_conversation"
    REFERRED = "referred"
    CLOSED = "closed"


STAGE_LABELS: dict[Stage, str] = {
    Stage.NOT_CONTACTED: "Not contacted",
    Stage.AWAITING_REPLY: "Awaiting reply",
    Stage.IN_CONVERSATION: "In conversation",
    Stage.REFERRED: "Referred",
    Stage.CLOSED: "Closed",
}


@dataclass(slots=True)
class InteractionEntry:
    """One dated exchange."""

    id: uuid.UUID
    kind: Kind
    direction: str
    summary: str
    occurred_at: datetime
    channel: str | None = None
    application_id: uuid.UUID | None = None

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind.value)


@dataclass(slots=True)
class ContactState:
    """A contact, folded. Every field is observed."""

    contact_id: uuid.UUID
    name: str
    timeline: list[InteractionEntry] = field(default_factory=list)

    @property
    def has_replied(self) -> bool:
        return any(e.direction == "inbound" for e in self.timeline)

    @property
    def last_outbound_at(self) -> datetime | None:
        """When the operator last sent something that expects an answer."""
        outbound = [
            e.occurred_at
            for e in self.timeline
            if e.direction == "outbound" and e.kind in AWAITING_KINDS
        ]
        return max(outbound) if outbound else None

    @property
    def last_inbound_at(self) -> datetime | None:
        inbound = [e.occurred_at for e in self.timeline if e.direction == "inbound"]
        return max(inbound) if inbound else None

    @property
    def last_interaction_at(self) -> datetime | None:
        return max((e.occurred_at for e in self.timeline), default=None)

    @property
    def spoke_at(self) -> datetime | None:
        """When a real conversation last happened, as opposed to a message sent."""
        spoken = [e.occurred_at for e in self.timeline if e.kind is Kind.CONVERSATION]
        return max(spoken) if spoken else None

    @property
    def referral_confirmed(self) -> bool:
        return any(e.kind is Kind.REFERRAL_CONFIRMED for e in self.timeline)

    @property
    def referral_asked(self) -> bool:
        return any(e.kind is Kind.REFERRAL_ASKED for e in self.timeline)

    @property
    def unanswered_outreach(self) -> int:
        """Messages sent since they last said anything.

        This is what caps the follow-up sequence. Counting all outreach ever
        would keep a revived thread permanently at its limit, which is wrong --
        a reply resets the relationship.
        """
        since = self.last_inbound_at
        return sum(
            1
            for e in self.timeline
            if e.direction == "outbound"
            and e.kind in AWAITING_KINDS
            and (since is None or e.occurred_at > since)
        )

    @property
    def stage(self) -> Stage:
        if self.referral_confirmed:
            return Stage.REFERRED
        if not self.timeline:
            return Stage.NOT_CONTACTED
        if self.has_replied:
            last_out, last_in = self.last_outbound_at, self.last_inbound_at
            if last_out and last_in and last_out > last_in:
                return Stage.AWAITING_REPLY
            return Stage.IN_CONVERSATION
        return Stage.AWAITING_REPLY

    def days_since_last_outbound(self, today: date | None = None) -> int | None:
        sent = self.last_outbound_at
        if sent is None:
            return None
        reference = today or datetime.now(UTC).date()
        return max(0, (reference - sent.date()).days)

    def silence_note(self, today: date | None = None) -> str | None:
        """The dated statement of silence, or nothing when there is nothing to
        say. Silent on day zero and once they have replied more recently than
        you wrote -- the ball is not in their court then."""
        if self.stage is not Stage.AWAITING_REPLY:
            return None
        days = self.days_since_last_outbound(today)
        if not days:
            return None
        return f"{days} day{'s' if days != 1 else ''} since you wrote, no reply"


def fold(contact: Contact, interactions: Sequence[ContactInteraction]) -> ContactState:
    """Fold a contact's interactions into its current state."""
    timeline = [
        InteractionEntry(
            id=i.id,
            kind=Kind(i.kind) if i.kind in set(Kind) else Kind.NOTE,
            direction=i.direction,
            summary=i.summary or "",
            occurred_at=i.occurred_at,
            channel=i.channel,
            application_id=i.application_id,
        )
        for i in interactions
    ]
    timeline.sort(key=lambda e: e.occurred_at)
    return ContactState(contact_id=contact.id, name=contact.name, timeline=timeline)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


@dataclass(slots=True)
class ContactInput:
    name: str
    company_name: str | None = None
    role_title: str | None = None
    relationship_type: str = Relationship.COLD.value
    school: str | None = None
    grad_year: int | None = None
    strength: int | None = None
    email: str | None = None
    profile_url: str | None = None
    notes: str | None = None

    def validated(self) -> ContactInput:
        if not self.name.strip():
            raise ValueError("a contact needs a name")
        if self.relationship_type not in set(Relationship):
            raise ValueError(
                f"unknown relationship {self.relationship_type!r}; "
                f"expected one of {sorted(r.value for r in Relationship)}"
            )
        if self.strength is not None and not 1 <= self.strength <= 5:
            raise ValueError("strength is 1-5, or left unset")
        return self


def _operator_id() -> uuid.UUID:
    from ..core.config import get_settings

    return get_settings().operator_id


def _resolve_company(session: Session, company_name: str | None) -> uuid.UUID | None:
    """Link a pasted company name to a known company, if one matches.

    Deliberately exact-on-canonical rather than fuzzy. A contact wrongly
    attached to the wrong employer would put their name beside the wrong
    postings, and an unlinked contact is a much smaller problem than a
    confidently wrong one.
    """
    if not company_name or not company_name.strip():
        return None
    key = canonical_company(company_name)
    return session.scalar(select(Company.id).where(Company.canonical_name == key))


def add_contact(
    session: Session, data: ContactInput, *, user_id: uuid.UUID | None = None
) -> Contact:
    data.validated()
    contact = Contact(
        user_id=user_id or _operator_id(),
        name=data.name.strip(),
        company_name=(data.company_name or "").strip() or None,
        company_id=_resolve_company(session, data.company_name),
        role_title=(data.role_title or "").strip() or None,
        relationship_type=data.relationship_type,
        school=(data.school or "").strip() or None,
        grad_year=data.grad_year,
        strength=data.strength,
        email=(data.email or "").strip() or None,
        profile_url=(data.profile_url or "").strip() or None,
        notes=(data.notes or "").strip() or None,
    )
    session.add(contact)
    session.flush()
    return contact


def update_contact(session: Session, contact_id: uuid.UUID, data: ContactInput) -> Contact | None:
    contact = session.get(Contact, contact_id)
    if contact is None:
        return None
    data.validated()
    contact.name = data.name.strip()
    contact.company_name = (data.company_name or "").strip() or None
    contact.company_id = _resolve_company(session, data.company_name)
    contact.role_title = (data.role_title or "").strip() or None
    contact.relationship_type = data.relationship_type
    contact.school = (data.school or "").strip() or None
    contact.grad_year = data.grad_year
    contact.strength = data.strength
    contact.email = (data.email or "").strip() or None
    contact.profile_url = (data.profile_url or "").strip() or None
    contact.notes = (data.notes or "").strip() or None
    session.flush()
    return contact


def delete_contact(session: Session, contact_id: uuid.UUID) -> bool:
    contact = session.get(Contact, contact_id)
    if contact is None:
        return False
    session.delete(contact)
    return True


def log_interaction(
    session: Session,
    contact: Contact,
    kind: str,
    *,
    summary: str = "",
    channel: str | None = None,
    direction: str | None = None,
    occurred_at: datetime | None = None,
    application_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> ContactInteraction:
    """Record an exchange. Raises ``ValueError`` on an unknown kind.

    ``direction`` defaults from the kind, because getting it wrong silently
    breaks the follow-up engine: a reply logged as outbound would look like
    another unanswered message from you.
    """
    if kind not in set(Kind):
        raise ValueError(
            f"unknown interaction kind {kind!r}; expected one of {sorted(k.value for k in Kind)}"
        )
    resolved_direction = direction or (
        "inbound" if Kind(kind) is Kind.REPLY else "outbound"
    )
    if resolved_direction not in {"inbound", "outbound"}:
        raise ValueError("direction is 'inbound' or 'outbound'")

    interaction = ContactInteraction(
        user_id=user_id or _operator_id(),
        contact_id=contact.id,
        application_id=application_id,
        kind=kind,
        channel=channel,
        direction=resolved_direction,
        summary=summary.strip(),
        occurred_at=occurred_at or datetime.now(UTC),
    )
    session.add(interaction)
    session.flush()
    return interaction


def list_contacts(
    session: Session, *, user_id: uuid.UUID | None = None
) -> list[tuple[Contact, ContactState]]:
    """Every contact with its folded state, most recent activity first.

    Two queries whatever the size of the list: the interactions are loaded with
    the contacts rather than per row.
    """
    uid = user_id or _operator_id()
    contacts = list(
        session.scalars(
            select(Contact)
            .where(Contact.user_id == uid)
            .options(selectinload(Contact.interactions))
        )
    )
    rows = [(c, fold(c, c.interactions)) for c in contacts]
    epoch = datetime.min.replace(tzinfo=UTC)
    rows.sort(key=lambda row: row[1].last_interaction_at or epoch, reverse=True)
    return rows


def get_contact(
    session: Session, contact_id: uuid.UUID, *, user_id: uuid.UUID | None = None
) -> tuple[Contact, ContactState] | None:
    contact = session.get(Contact, contact_id)
    if contact is None or contact.user_id != (user_id or _operator_id()):
        return None
    return contact, fold(contact, contact.interactions)
