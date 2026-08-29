"""Measures the corpus against the postings currently ingested.

Reports, per fact, the skill terms it contributes and how many sampled postings
mention them, plus the postings no *other* fact reaches. All counts, over a
stated sample of postings that carry a real description.
"""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.models import CorpusFact, Posting
from ..core.textanalysis import display_form, is_technical, profile
from .match import CORE_THRESHOLD, carries_signal

# The market index is built from postings carrying a description. Below this
# many, the sample is too small for a "the market wants X" claim to be worth
# making, and the caller is told so rather than shown a confident-looking list.
MIN_MEANINGFUL_SAMPLE = 25

# How many postings to read when building the index. Descriptions are long, and
# the counts stop moving well before this; the cap keeps a cold page load quick.
MAX_SAMPLE = 1500


@dataclass(slots=True)
class TermDemand:
    """How often one term shows up across the sampled postings."""

    term: str
    display: str
    # Postings that mention the term at all.
    posting_count: int
    # Postings that lean on it hard enough to read as central to the role.
    core_count: int
    is_technical: bool


class MarketIndex:
    """Term demand measured across postings that carry a real description.

    Holds, per term, the set of sampled postings that mention it. Sets rather
    than counters because the interesting questions are unions ("how many
    postings does this fact reach in total, without double-counting?"), and
    exact set arithmetic is both cheap at this scale and impossible to fudge.
    """

    def __init__(self, documents: list[str]) -> None:
        self.sample_size = len(documents)
        self.postings_by_term: dict[str, set[int]] = {}
        self._demand: dict[str, TermDemand] = {}

        core_hits: dict[str, int] = {}
        surfaces: dict[str, str] = {}

        for idx, text in enumerate(documents):
            prof = profile(text)
            for term, occurrences in prof.counts.items():
                if not carries_signal(term, occurrences):
                    continue
                self.postings_by_term.setdefault(term, set()).add(idx)
                if occurrences >= CORE_THRESHOLD:
                    core_hits[term] = core_hits.get(term, 0) + 1
                surfaces.setdefault(term, prof.display(term))

        for term, postings in self.postings_by_term.items():
            self._demand[term] = TermDemand(
                term=term,
                display=surfaces.get(term) or display_form(term),
                posting_count=len(postings),
                core_count=core_hits.get(term, 0),
                is_technical=is_technical(term),
            )

    @property
    def is_meaningful(self) -> bool:
        return self.sample_size >= MIN_MEANINGFUL_SAMPLE

    def demand(self, term: str) -> TermDemand | None:
        return self._demand.get(term)

    def reach(self, terms: set[str]) -> set[int]:
        """Sampled postings mentioning at least one of ``terms``."""
        reached: set[int] = set()
        for term in terms:
            reached |= self.postings_by_term.get(term, set())
        return reached

    def in_demand(self, limit: int | None = 60, *, skills_only: bool = True) -> list[TermDemand]:
        """The most widely demanded terms, most postings first. ``limit=None``
        returns the whole ranking.

        ``skills_only`` restricts this to recognised skill vocabulary. A general
        word repeated within one posting is signal about that role, but across a
        whole market the top of the list is just "engineer", "software",
        "technology" -- nothing anyone can act on.
        """
        candidates = [d for d in self._demand.values() if d.is_technical or not skills_only]
        ranked = sorted(candidates, key=lambda d: (-d.posting_count, -d.core_count, d.term))
        return ranked if limit is None else ranked[:limit]


@dataclass(slots=True)
class FactContribution:
    """One fact, and what it buys in the sampled market."""

    fact_id: str
    fact_type: str
    title: str
    # Terms this fact contributes that anything in the market asks for, ranked
    # by how many postings ask for them.
    terms: list[TermDemand] = field(default_factory=list)
    # Postings mentioning at least one of this fact's terms.
    reach: int = 0
    # Of those, the ones no other fact reaches. This is what makes a fact worth
    # keeping on the resume rather than merely true.
    unique_reach: int = 0
    # Terms the fact contributes that no sampled posting asks for. Not a
    # judgement -- the sample may simply not cover the operator's field.
    unmatched_term_count: int = 0

    @property
    def carries_market_weight(self) -> bool:
        return self.reach > 0


@dataclass(slots=True)
class CorpusCoverage:
    """The corpus measured against the market, with the sample stated."""

    sample_size: int
    is_meaningful: bool
    fact_count: int
    contributions: list[FactContribution] = field(default_factory=list)
    # Postings reached by at least one fact, deduplicated across the corpus.
    reached: int = 0
    # Terms the market emphasises that no fact evidences, most demanded first.
    gaps: list[TermDemand] = field(default_factory=list)
    # Which slice of the market this was measured against. Empty means all of
    # it, which is only the right comparison for someone whose field the
    # description-bearing postings actually cover.
    role_families: tuple[str, ...] = ()

    @property
    def unreached(self) -> int:
        return max(0, self.sample_size - self.reached)

    def basis(self) -> str:
        """The sample, stated plainly. Shown next to every number above."""
        if self.sample_size == 0:
            return "No postings with descriptions have been ingested yet."
        scope = (
            " in " + ", ".join(sorted(self.role_families))
            if self.role_families
            else ""
        )
        basis = (
            f"Counted across {self.sample_size} postings{scope} that carry a full description."
        )
        if not self.is_meaningful:
            basis += " That is a small sample — treat these counts as indicative only."
        return basis


def _fact_terms(fact: CorpusFact) -> set[str]:
    """The signal terms one fact contributes.

    Uses the same rule as the match engine, so a term that would count toward a
    posting's score is exactly the set of terms shown here.
    """
    prof = profile(f"{fact.title}\n{fact.body}".strip())
    return {term for term, occurrences in prof.counts.items() if carries_signal(term, occurrences)}


def analyse(facts: list[CorpusFact], market: MarketIndex, *, gap_limit: int = 25) -> CorpusCoverage:
    """Measure a corpus against a market index.

    Pure: takes the facts and the index, returns counts. The database work
    happens in :func:`corpus_coverage`.
    """
    terms_by_fact: dict[str, set[str]] = {str(f.id): _fact_terms(f) for f in facts}
    reach_by_fact: dict[str, set[int]] = {
        fid: market.reach(terms) for fid, terms in terms_by_fact.items()
    }

    contributions: list[FactContribution] = []
    for fact in facts:
        fid = str(fact.id)
        terms = terms_by_fact[fid]
        demanded = [d for d in (market.demand(t) for t in terms) if d is not None]
        demanded.sort(key=lambda d: (-d.posting_count, -d.core_count, d.term))

        # Postings this fact reaches that no *other* fact does.
        others: set[int] = set()
        for other_id, reached in reach_by_fact.items():
            if other_id != fid:
                others |= reached

        contributions.append(
            FactContribution(
                fact_id=fid,
                fact_type=fact.fact_type,
                title=fact.title,
                terms=demanded,
                reach=len(reach_by_fact[fid]),
                unique_reach=len(reach_by_fact[fid] - others),
                unmatched_term_count=len(terms) - len(demanded),
            )
        )

    # Most valuable first, but a fact that reaches nothing still has to be
    # visible -- that absence is the point.
    contributions.sort(key=lambda c: (-c.reach, -c.unique_reach, c.title))

    evidenced: set[str] = set().union(*terms_by_fact.values()) if terms_by_fact else set()
    # Filter first, then take. Drawing a fixed window and filtering inside it
    # starves the list exactly when the corpus is good: a corpus evidencing most
    # of the top terms would return a handful of gaps while real ones sat just
    # below the window. The full ranking is a few thousand entries and already
    # in memory, so ranking it whole costs nothing worth saving.
    gaps = [d for d in market.in_demand(limit=None) if d.term not in evidenced][:gap_limit]

    all_reached: set[int] = set()
    for reached in reach_by_fact.values():
        all_reached |= reached

    return CorpusCoverage(
        sample_size=market.sample_size,
        is_meaningful=market.is_meaningful,
        fact_count=len(facts),
        contributions=contributions,
        reached=len(all_reached),
        gaps=gaps,
    )


class _MarketCache:
    """Caches market indexes per role-family filter.

    Building one reads and tokenises every sampled description, which is far too
    slow to repeat on each page load. The key includes the posting count and the
    latest sighting, so an ingest run invalidates it automatically.
    """

    MAX_ENTRIES = 6

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple, MarketIndex] = OrderedDict()

    def get(self, session: Session, role_families: tuple[str, ...]) -> MarketIndex:
        stamp = session.execute(
            select(func.count(Posting.id), func.max(Posting.last_seen_at)).where(
                Posting.description_available.is_(True), Posting.is_active.is_(True)
            )
        ).one()
        key = (role_families, *stamp)

        with self._lock:
            hit = self._entries.get(key)
            if hit is not None:
                self._entries.move_to_end(key)
                return hit

        index = MarketIndex(_market_documents(session, role_families))

        with self._lock:
            self._entries[key] = index
            self._entries.move_to_end(key)
            while len(self._entries) > self.MAX_ENTRIES:
                self._entries.popitem(last=False)
        return index


def _market_documents(session: Session, role_families: tuple[str, ...]) -> list[str]:
    stmt = select(Posting.title, Posting.description).where(
        Posting.description_available.is_(True),
        Posting.is_active.is_(True),
        Posting.description.isnot(None),
    )
    if role_families:
        stmt = stmt.where(Posting.role_family.in_(role_families))
    # Newest first: if the cap bites, it should bite on stale rows.
    stmt = stmt.order_by(Posting.last_seen_at.desc()).limit(MAX_SAMPLE)
    return [f"{title}\n{description}" for title, description in session.execute(stmt)]


_cache = _MarketCache()


def market_index(session: Session, role_families: tuple[str, ...] = ()) -> MarketIndex:
    return _cache.get(session, role_families)


def corpus_coverage(
    session: Session,
    *,
    role_families: tuple[str, ...] = (),
    user_id: uuid.UUID | None = None,
    gap_limit: int = 25,
) -> CorpusCoverage:
    """The operator's corpus measured against the current market."""
    from ..core.corpus import list_facts

    facts = list_facts(session, user_id=user_id)
    report = analyse(facts, market_index(session, role_families), gap_limit=gap_limit)
    report.role_families = role_families
    return report
