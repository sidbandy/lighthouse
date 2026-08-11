"""What to study, derived from the jobs the operator actually applied to.

Every other study tool hands you the same list as everyone else. This one starts
from the postings on your own board: read what they require, subtract what your
corpus can already evidence, and what is left is the real list -- in the order
your own applications weight it.

That is the connection the whole product is built on. Discover found the roles,
Track recorded which ones you sent, the corpus knows what you can back up, and
the difference between those two is a study plan nobody had to write.

Two rules keep it honest. A topic is only recommended when the postings named
its language, not because it is generally good for you; and the count of
applications asking for it travels with it, so "3 of your 9 applications" is
checkable rather than a ranking you are asked to trust.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.corpus import corpus_documents
from ..core.models import Application, Posting
from ..core.textanalysis import is_technical, profile
from ..discover.match import build_index
from .catalog import TOPICS, Resource, Topic

# A topic named by fewer applications than this is noise: one posting mentioning
# "kubernetes" once is not a reason to spend a weekend on it.
MIN_APPLICATIONS = 1


@dataclass(slots=True)
class TopicNeed:
    """One topic, and the evidence that it is worth the operator's time."""

    topic: Topic
    # Applications whose posting asked for this. The number that makes the
    # recommendation checkable.
    application_count: int
    total_applications: int
    # The exact words in those postings that triggered it, so the operator can
    # go and read them.
    matched_terms: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    # True when the corpus already evidences the trigger terms -- worth a
    # refresher rather than a first pass.
    partially_covered: bool = False

    @property
    def slug(self) -> str:
        return self.topic.slug

    def statement(self) -> str:
        where = ", ".join(self.companies[:3])
        tail = f" ({where})" if where else ""
        covered = (
            " Your corpus already touches this, so it is a refresher."
            if self.partially_covered
            else ""
        )
        verb = "asks" if self.application_count == 1 else "ask"
        return (
            f"{self.application_count} of your {self.total_applications} applications "
            f"{verb} for this{tail}.{covered}"
        )

    @property
    def resources(self) -> tuple[Resource, ...]:
        return self.topic.resources


@dataclass(slots=True)
class Curriculum:
    """Everything the operator's own applications imply they should study."""

    total_applications: int
    needs: list[TopicNeed] = field(default_factory=list)
    # Terms the postings emphasised that no topic in the catalogue covers. Shown
    # rather than swallowed: the catalogue is hand-maintained and will always be
    # behind the market, and pretending otherwise hides the gap.
    uncatalogued: list[tuple[str, int]] = field(default_factory=list)

    def note(self) -> str:
        if self.total_applications == 0:
            return (
                "Nothing to derive a plan from yet. Apply to a few roles and this page "
                "builds itself out of what they actually asked for."
            )
        if not self.needs:
            return (
                f"Across {self.total_applications} applications, nothing in the catalogue "
                "came up often enough to be worth a study block. That is a real answer — "
                "spend the time on problems instead."
            )
        top = self.needs[0]
        return (
            f"From {self.total_applications} applications. Biggest gap: {top.topic.name}, "
            f"asked for by {top.application_count}."
        )


def _operator_id() -> uuid.UUID:
    from ..core.config import get_settings

    return get_settings().operator_id


def build(session: Session, *, user_id: uuid.UUID | None = None) -> Curriculum:
    """Read the operator's applied-to postings into a study list.

    Only postings that carry a real description are read, because a title alone
    cannot say what a role requires -- and a recommendation built on a guess is
    the thing this module exists not to produce.
    """
    uid = user_id or _operator_id()

    postings = list(
        session.scalars(
            select(Posting)
            .join(Application, Application.posting_id == Posting.id)
            .where(Application.user_id == uid, Posting.description_available.is_(True))
        )
    )
    total_applications = int(
        session.scalar(
            select(func.count(Application.id)).where(Application.user_id == uid)
        )
        or 0
    )

    if not postings:
        return Curriculum(total_applications=total_applications)

    index = build_index(corpus_documents(session, user_id=uid))
    corpus_terms = set(index.combined.terms)

    hits: dict[str, list[tuple[str, set[str]]]] = {t.slug: [] for t in TOPICS}
    emphasised: Counter[str] = Counter()
    covered_triggers: dict[str, bool] = {}

    for posting in postings:
        text = f"{posting.title}\n{posting.description or ''}".lower()
        prof = profile(text)
        company = posting.company.name if posting.company else "a company"

        for term, count in prof.counts.most_common():
            if is_technical(term) and count >= 2:
                emphasised[term] += 1

        for topic in TOPICS:
            matched = {t for t in topic.triggers if t in text}
            if matched:
                hits[topic.slug].append((company, matched))

    needs: list[TopicNeed] = []
    for topic in TOPICS:
        rows = hits[topic.slug]
        if len(rows) < MIN_APPLICATIONS:
            continue
        terms: set[str] = set()
        companies: list[str] = []
        for company, matched in rows:
            terms |= matched
            if company not in companies:
                companies.append(company)
        # A trigger the corpus already evidences means the operator has touched
        # this; the topic is still worth listing, but as a refresher.
        covered = any(
            any(word in corpus_terms for word in term.split()) for term in terms
        )
        covered_triggers[topic.slug] = covered
        needs.append(
            TopicNeed(
                topic=topic,
                application_count=len(rows),
                total_applications=total_applications,
                matched_terms=sorted(terms),
                companies=companies,
                partially_covered=covered,
            )
        )

    needs.sort(key=lambda n: (-n.application_count, n.partially_covered, n.topic.name))

    catalogued = {t for topic in TOPICS for trigger in topic.triggers for t in trigger.split()}
    uncatalogued = [
        (term, count)
        for term, count in emphasised.most_common(40)
        if term not in catalogued and term not in corpus_terms
    ][:12]

    return Curriculum(
        total_applications=total_applications,
        needs=needs,
        uncatalogued=uncatalogued,
    )
