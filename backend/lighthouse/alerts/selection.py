"""Choosing which new postings are worth an alert.

Every filter here is a reason not to send. The default is silence, because the
cost of the two failure modes is not symmetric: a missed alert costs the
operator a scroll through Discover, and a noisy one costs them the habit of
reading alerts at all -- after which every future alert is worthless too.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from ..core.models import Posting
from ..core.onboarding import load_profile
from ..discover import eligibility, ghost, ranking, service

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AlertCandidate:
    """One posting worth telling the operator about, and why."""

    posting_id: str
    title: str
    company_name: str
    url: str
    match_score: int
    term_label: str | None
    location: str | None
    ghost_label: str
    top_gaps: list[str]
    is_thin_evidence: bool

    @property
    def evidence_note(self) -> str:
        """Said plainly, because a score from a title alone is weak evidence
        and the operator should weigh it that way before spending an hour."""
        if self.is_thin_evidence:
            return "scored from the title only"
        return "scored against the full description"


def select_new_postings(
    session: Session,
    *,
    since: datetime,
    min_match: int,
    skip_ghost: tuple[str, ...] = (),
    limit: int = 25,
    today: date | None = None,
) -> list[AlertCandidate]:
    """Postings first seen after ``since`` that clear every bar.

    ``since`` is when Lighthouse first saw the row, not when the employer
    posted it: ``posted_at`` is frequently missing and frequently wrong, and a
    posting that appeared on a feed today is new to the operator regardless of
    the date it carries.
    """
    today = today or datetime.now(UTC).date()

    filters = service.PostingFilters(
        first_seen_after=since,
        active_only=True,
        # An alert for a cycle that has already started is noise by definition.
        applyable_only=True,
        # Generous: the match and ghost bars below do the real narrowing, and
        # scoring is what tells us which of these are worth anything.
        limit=500,
    )
    scored = ranking.score_postings(session, filters, today=today)
    if not scored:
        return []

    # Loaded once. The operator's graduation year does not change mid-run, and
    # this is the only thing the eligibility check needs from them.
    profile = load_profile(session)
    graduation_year = profile.graduation_year if profile else None

    out: list[AlertCandidate] = []
    for item in scored:
        if item.match.score < min_match:
            continue

        posting = session.get(Posting, item.summary.id)
        if posting is None:  # pragma: no cover - row deleted mid-run
            continue

        assessment = ghost.assess(
            posting, source_count=item.summary.source_count, today=today
        )
        if assessment.label.value in skip_ghost:
            continue

        # A knockout the operator cannot clear is not an opportunity. Only a
        # stated NOT_ELIGIBLE drops the posting -- NOT_STATED is kept, because
        # refusing to alert on an unknown window would hide real roles, and
        # that is the more expensive mistake of the two.
        check = eligibility.check_graduation(
            posting.description,
            graduation_year=graduation_year,
            employment_type=posting.employment_type,
        )
        if check.verdict is eligibility.Verdict.NOT_ELIGIBLE:
            continue

        out.append(
            AlertCandidate(
                posting_id=str(posting.id),
                title=item.summary.title,
                company_name=item.summary.company_name,
                url=posting.url or posting.canonical_url,
                match_score=item.match.score,
                term_label=item.summary.term_label,
                location=(item.summary.location_labels or [None])[0],
                ghost_label=assessment.label.value,
                top_gaps=[t.term for t in item.match.gaps[:3]],
                is_thin_evidence=item.match.is_thin_evidence,
            )
        )
        if len(out) >= limit:
            break

    logger.info("alerts: %d of %d new postings cleared the bar", len(out), len(scored))
    return out
