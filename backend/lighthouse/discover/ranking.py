"""Scoring and laning the posting list against the operator's corpus.

This is where the corpus meets the postings. It builds the match index once,
scores a filtered set of postings, assigns lanes, and returns the pieces the UI
needs: the ranked list, and the three lanes with their quotas.

The corpus index is cached and rebuilt only when the corpus changes, so opening
Discover does not re-tokenise every fact each time.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core import corpus as corpus_service
from ..core.models import Company, CorpusFact, Posting
from . import lanes, match, service
from .lanes import Lane, LaneAssignment
from .schemas import (
    LaneBucketOut,
    LaneOut,
    MatchOut,
    ScoredPostingOut,
    TermMatchOut,
)


@dataclass(slots=True)
class ScoredPosting:
    summary: service.PostingSummary
    match: match.MatchResult
    lane: LaneAssignment


class _IndexCache:
    """Caches the match index, invalidated when the corpus changes.

    Keyed on the corpus's row count and latest update time, which is a cheap
    query and changes whenever a fact is added, edited or removed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: tuple[int, datetime | None] | None = None
        self._index: match.CorpusIndex | None = None

    def get(self, session: Session) -> match.CorpusIndex:
        key = session.execute(
            select(func.count(CorpusFact.id), func.max(CorpusFact.updated_at))
        ).one()
        with self._lock:
            if self._index is None or self._key != key:
                self._index = match.build_index(corpus_service.corpus_documents(session))
                self._key = key
            return self._index


_cache = _IndexCache()


def _company_lookup(session: Session, posting_ids: list) -> dict:
    """canonical_name and tier per posting company, in one query."""
    rows = session.execute(
        select(Posting.id, Company.canonical_name, Company.tier)
        .join(Company, Company.id == Posting.company_id)
        .where(Posting.id.in_(posting_ids))
    ).all()
    return {pid: (canonical, tier) for pid, canonical, tier in rows}


def score_postings(
    session: Session,
    filters: service.PostingFilters,
    *,
    today: date | None = None,
) -> list[ScoredPosting]:
    """Score and lane a filtered page of postings."""
    index = _cache.get(session)
    summaries, _ = service.list_postings(session, filters, today)
    if not summaries:
        return []

    companies = _company_lookup(session, [s.id for s in summaries])

    scored: list[ScoredPosting] = []
    for summary in summaries:
        posting = session.get(Posting, summary.id)
        result = match.match(
            title=posting.title,
            description=posting.description,
            index=index,
            company_name=summary.company_name,
        )
        canonical, tier = companies.get(summary.id, ("", None))
        selectivity = lanes.selectivity_of(canonical, tier)
        assignment = lanes.assign_lane(
            match_score=result.score,
            selectivity=selectivity,
            thin_evidence=result.is_thin_evidence,
        )
        scored.append(ScoredPosting(summary=summary, match=result, lane=assignment))

    # Reliable matches first. A 100% coverage computed from three comparable
    # terms is not more trustworthy than a solid 48 from twenty, so
    # thin-evidence postings are ranked below fully-compared ones regardless of
    # their headline number. Within each group, best match first; an empty
    # corpus leaves every score at 0 and preserves the query's recency order.
    scored.sort(key=lambda s: (s.match.is_thin_evidence, -s.match.score, -s.match.rarity))
    return scored


@dataclass(slots=True)
class LaneBucket:
    lane: Lane
    weekly_quota: int
    postings: list[ScoredPosting]


def three_lane_view(
    session: Session,
    filters: service.PostingFilters,
    *,
    per_lane: int = 25,
    today: date | None = None,
) -> list[LaneBucket]:
    """Split scored postings into reach / target / safety.

    Each lane is capped independently so an abundance of safeties cannot crowd
    the reaches off the screen -- the whole point of separating them.
    """
    # Pull a wider slice than one page so each lane has enough to fill.
    wide = replace(filters, limit=max(filters.limit, per_lane * 6), offset=0)
    scored = score_postings(session, wide, today=today)

    buckets: dict[Lane, list[ScoredPosting]] = {lane: [] for lane in Lane}
    for item in scored:
        buckets[item.lane.lane].append(item)

    # Always return all three lanes, even when one is empty, so the layout is
    # stable and the operator can see that a lane (often Safety) has nothing in
    # it yet -- which is itself information.
    return [
        LaneBucket(
            lane=lane,
            weekly_quota=lanes.WEEKLY_QUOTA[lane],
            postings=buckets[lane][:per_lane],
        )
        for lane in (Lane.REACH, Lane.TARGET, Lane.SAFETY)
    ]


def invalidate_cache() -> None:
    """Force an index rebuild. Called after the corpus is edited so the next
    score reflects the change immediately."""
    global _cache
    _cache = _IndexCache()


# --------------------------------------------------------------------------
# Serialisation to API shapes
# --------------------------------------------------------------------------


def _term_out(term: match.TermMatch) -> TermMatchOut:
    return TermMatchOut(
        term=term.display,
        posting_count=term.posting_count,
        corpus_count=term.corpus_count,
        is_technical=term.is_technical,
        emphasis=term.emphasis,
        component_evidence=term.component_evidence,
    )


def match_to_out(result: match.MatchResult) -> MatchOut:
    return MatchOut(
        score=result.score,
        evidence_basis=result.evidence_basis,
        thin_evidence=result.is_thin_evidence,
        summary=result.summary(),
        matched=[_term_out(t) for t in result.matched],
        reword=[_term_out(t) for t in result.wording],
        gaps=[_term_out(t) for t in result.gaps],
    )


def scored_to_out(item: ScoredPosting) -> ScoredPostingOut:
    return ScoredPostingOut(
        **item.summary.model_dump(),
        match=match_to_out(item.match),
        lane=LaneOut(
            lane=item.lane.lane.value,
            selectivity=item.lane.selectivity,
            reason=item.lane.reason,
        ),
    )


def lane_view_to_out(buckets: list[LaneBucket]) -> list[LaneBucketOut]:
    return [
        LaneBucketOut(
            lane=bucket.lane.value,
            weekly_quota=bucket.weekly_quota,
            count=len(bucket.postings),
            postings=[scored_to_out(p) for p in bucket.postings],
        )
        for bucket in buckets
    ]


def match_for_posting(session: Session, posting: Posting) -> MatchOut | None:
    """Score a single posting for its detail view.

    Returns ``None`` when the corpus is empty -- there is nothing to match
    against, and a row of zeros would be noise rather than information.
    """
    index = _cache.get(session)
    if index.is_empty:
        return None
    return match_to_out(
        match.match(
            title=posting.title,
            description=posting.description,
            index=index,
            company_name=posting.company.name if posting.company else None,
        )
    )
