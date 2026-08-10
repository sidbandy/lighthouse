"""The school angle, and where the network is thin.

A student's one reliable edge is that someone at the company went to their
school. Lighthouse does not go and find those people -- that would mean scraping
LinkedIn, which is a hard boundary here. LinkedIn's own Alumni tool does the
finding, and it is a first-party feature built for exactly this; what it cannot
do is tell you which of those names is worth writing to, which is the part this
module answers.

The useful question is not "who do I know" but **"which companies I actually
want do I have nobody at"**, because that gap is the thing an afternoon on the
Alumni page can close.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.models import Company, Contact, OperatorProfile, OperatorTarget, Posting


@dataclass(slots=True)
class CompanyCoverage:
    """One target company and who the operator knows there."""

    company_id: uuid.UUID | None
    company_name: str
    contact_count: int
    alumni_count: int
    open_postings: int
    is_target: bool

    @property
    def has_nobody(self) -> bool:
        return self.contact_count == 0

    def note(self) -> str:
        if self.contact_count == 0:
            return "Nobody yet — the gap worth closing."
        who = f"{self.contact_count} contact{'s' if self.contact_count != 1 else ''}"
        if self.alumni_count:
            return f"{who}, {self.alumni_count} from your school."
        return who


@dataclass(slots=True)
class NetworkOverview:
    school: str | None
    total_contacts: int
    alumni_contacts: int
    coverage: list[CompanyCoverage]

    @property
    def uncovered_targets(self) -> list[CompanyCoverage]:
        return [c for c in self.coverage if c.is_target and c.has_nobody]

    def note(self) -> str:
        if not self.school:
            return (
                "Set your school on My corpus and Lighthouse can mark which contacts "
                "are alumni — it is the one introduction that reliably gets answered."
            )
        if self.total_contacts == 0:
            return (
                f"No contacts yet. LinkedIn's Alumni tool on the {self.school} page, "
                "filtered by where they work, is the fastest way to a first list — "
                "paste the names in and Lighthouse handles the rest."
            )
        gaps = self.uncovered_targets
        if gaps:
            names = ", ".join(c.company_name for c in gaps[:3])
            return f"{self.total_contacts} contacts. No one yet at {names}."
        return f"{self.total_contacts} contacts, {self.alumni_contacts} from {self.school}."


def _operator_id() -> uuid.UUID:
    from ..core.config import get_settings

    return get_settings().operator_id


def overview(session: Session, *, user_id: uuid.UUID | None = None) -> NetworkOverview:
    """Who the operator knows, against the companies they actually want.

    Target companies with nobody at them lead, because that is the list an hour
    of work can change. Companies they happen to know someone at but never
    marked as a target are included too, since a warm contact somewhere is a
    reason to look at the place.
    """
    uid = user_id or _operator_id()
    profile = session.scalar(select(OperatorProfile).where(OperatorProfile.user_id == uid))
    school = (getattr(profile, "school", None) or "").strip() or None

    contacts = list(session.scalars(select(Contact).where(Contact.user_id == uid)))
    alumni_total = sum(1 for c in contacts if is_alumni(c, school))

    targets = {
        row.company_id: row
        for row in session.scalars(select(OperatorTarget).where(OperatorTarget.user_id == uid))
    }
    company_ids = set(targets) | {c.company_id for c in contacts if c.company_id}
    names = dict(
        session.execute(
            select(Company.id, Company.name).where(Company.id.in_(company_ids or {uuid.uuid4()}))
        ).all()
    )
    counts = dict(
        session.execute(
            select(Posting.company_id, func.count(Posting.id))
            .where(
                Posting.company_id.in_(company_ids or {uuid.uuid4()}),
                Posting.is_active.is_(True),
            )
            .group_by(Posting.company_id)
        ).all()
    )

    coverage: list[CompanyCoverage] = []
    for cid in company_ids:
        at_company = [c for c in contacts if c.company_id == cid]
        coverage.append(
            CompanyCoverage(
                company_id=cid,
                company_name=names.get(cid, "Unknown company"),
                contact_count=len(at_company),
                alumni_count=sum(1 for c in at_company if is_alumni(c, school)),
                open_postings=int(counts.get(cid, 0)),
                is_target=cid in targets,
            )
        )

    # Unlinked contacts still tell the operator something, so companies we could
    # not resolve to a row are grouped under the name they typed.
    for contact in contacts:
        if contact.company_id is None and contact.company_name:
            existing = next(
                (
                    c
                    for c in coverage
                    if c.company_id is None and c.company_name == contact.company_name
                ),
                None,
            )
            if existing:
                existing.contact_count += 1
                existing.alumni_count += 1 if is_alumni(contact, school) else 0
            else:
                coverage.append(
                    CompanyCoverage(
                        company_id=None,
                        company_name=contact.company_name,
                        contact_count=1,
                        alumni_count=1 if is_alumni(contact, school) else 0,
                        open_postings=0,
                        is_target=False,
                    )
                )

    # Targets with nobody first: that is the actionable end of the list.
    coverage.sort(
        key=lambda c: (not (c.is_target and c.has_nobody), -c.open_postings, c.company_name)
    )
    return NetworkOverview(
        school=school,
        total_contacts=len(contacts),
        alumni_contacts=alumni_total,
        coverage=coverage,
    )


def is_alumni(contact: Contact, school: str | None) -> bool:
    """Same school, matched on the string the operator typed.

    Exact-ish rather than fuzzy on purpose: "University of Texas" and "UT
    Austin" are the same place and will not match, which is a miss the operator
    can fix by editing one field. Guessing they are the same when they are not
    puts a false "we're alumni" line into a real message.
    """
    if contact.relationship_type == "alumni":
        return True
    if not school or not contact.school:
        return False
    return contact.school.strip().lower() == school.strip().lower()
