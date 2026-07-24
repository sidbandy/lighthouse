"""Running an ingest: fetch, resolve, dedup, persist.

The pipeline's job is to be *safe* rather than clever. Two properties matter
more than throughput:

* **Isolation.** Each connector runs inside its own try/except. A source that
  changes layout, 404s or returns junk is recorded as unhealthy and skipped;
  every other source still lands.
* **A stale list beats a wrong one.** If a source returns less than half what
  it returned last time, that is treated as a parse failure, not as postings
  disappearing. Prior data is kept and the source is quarantined for review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from ..core.models import Company, Posting, PostingSource, SourceHealth
from .ats_targets import ats_connectors
from .base import Connector, RawPosting, build_client
from .dedup import MergedPosting, dedup_stats, deduplicate
from .normalize import classify_employment_type, classify_role_family, parse_sponsorship
from .registry import connectors_by_tier
from .seasons import is_applyable
from .terms import resolve_term

logger = logging.getLogger(__name__)

# A run returning less than this fraction of the previous run's rows is treated
# as a broken parse rather than as genuine attrition.
COLLAPSE_THRESHOLD = 0.5


@dataclass
class SourceResult:
    source_id: str
    ok: bool
    row_count: int = 0
    error: str | None = None
    quarantined: bool = False


@dataclass
class IngestReport:
    """What a run did, in enough detail to debug it later."""

    started_at: datetime
    finished_at: datetime | None = None
    sources: list[SourceResult] = field(default_factory=list)
    raw_count: int = 0
    merged_count: int = 0
    created: int = 0
    updated: int = 0
    skipped_not_applyable: int = 0
    term_rules: dict[str, int] = field(default_factory=dict)

    @property
    def failed_sources(self) -> list[SourceResult]:
        return [s for s in self.sources if not s.ok]

    def summary(self) -> str:
        ok = sum(1 for s in self.sources if s.ok)
        return (
            f"{ok}/{len(self.sources)} sources ok; {self.raw_count} raw -> "
            f"{self.merged_count} deduped; {self.created} new, {self.updated} updated"
        )


def fetch_source(connector: Connector, session: Session) -> tuple[list[RawPosting], SourceResult]:
    """Fetch one source and update its health record.

    Health is recorded whether or not the fetch succeeded, so a source that
    quietly stopped working is visible rather than merely absent.
    """
    health = session.get(SourceHealth, connector.source_id)
    if health is None:
        # Column defaults only apply at INSERT, so set the counter explicitly:
        # this record is read and incremented before it is ever flushed.
        health = SourceHealth(
            source_id=connector.source_id, consecutive_failures=0, is_quarantined=False
        )
        session.add(health)

    now = datetime.now(UTC)
    health.last_attempt_at = now

    try:
        with build_client() as client:
            rows = connector.fetch(client)
    except Exception as exc:  # noqa: BLE001 - per-source isolation is the point
        health.consecutive_failures += 1
        health.last_error = str(exc)[:500]
        logger.warning("source %s failed: %s", connector.source_id, exc)
        return [], SourceResult(connector.source_id, ok=False, error=str(exc))

    previous = health.last_row_count
    if previous and len(rows) < previous * COLLAPSE_THRESHOLD:
        health.consecutive_failures += 1
        health.is_quarantined = True
        health.last_error = (
            f"row count collapsed: {len(rows)} vs {previous} previously; keeping prior data"
        )
        logger.warning("source %s quarantined: %s", connector.source_id, health.last_error)
        return [], SourceResult(
            connector.source_id,
            ok=False,
            row_count=len(rows),
            error=health.last_error,
            quarantined=True,
        )

    health.previous_row_count = previous
    health.last_row_count = len(rows)
    health.last_success_at = now
    health.consecutive_failures = 0
    health.last_error = None
    health.is_quarantined = False
    return rows, SourceResult(connector.source_id, ok=True, row_count=len(rows))


def _get_or_create_company(session: Session, merged: MergedPosting, cache: dict) -> Company:
    key = merged.primary.canonical_company_name
    if key in cache:
        return cache[key]

    company = session.scalar(select(Company).where(Company.canonical_name == key))
    if company is None:
        company = Company(
            name=merged.company_name,
            canonical_name=key,
            ats_vendor=merged.ats_vendor,
        )
        session.add(company)
        session.flush()
    elif merged.ats_vendor and not company.ats_vendor:
        company.ats_vendor = merged.ats_vendor

    cache[key] = company
    return company


def persist(session: Session, merged_postings: list[MergedPosting], today: date) -> IngestReport:
    """Upsert deduplicated postings, keyed on canonical URL."""
    report = IngestReport(started_at=datetime.now(UTC))
    company_cache: dict[str, Company] = {}

    for merged in merged_postings:
        resolution = resolve_term(
            title=merged.title,
            description=merged.description,
            explicit_terms=merged.explicit_terms,
            today=today,
        )
        report.term_rules[resolution.rule] = report.term_rules.get(resolution.rule, 0) + 1

        if not is_applyable(resolution.cycle, today):
            report.skipped_not_applyable += 1
            continue

        company = _get_or_create_company(session, merged, company_cache)
        posting = session.scalar(
            select(Posting).where(Posting.canonical_url == merged.canonical_url)
        )
        is_new = posting is None
        if is_new:
            posting = Posting(canonical_url=merged.canonical_url, company_id=company.id)
            session.add(posting)

        posting.company_id = company.id
        posting.title = merged.title
        posting.normalized_title = merged.primary.normalized_title_value
        posting.url = merged.url
        posting.ats_job_id = merged.ats_job_id
        posting.description = merged.description
        posting.description_available = merged.description is not None
        posting.season = resolution.cycle.season if resolution.cycle else None
        posting.term_year = resolution.cycle.year if resolution.cycle else None
        posting.term_rule = resolution.rule
        posting.term_evidence = resolution.evidence
        posting.employment_type = classify_employment_type(merged.title, merged.employment_hint)
        posting.role_family = classify_role_family(merged.title)
        posting.sponsorship = parse_sponsorship(merged.sponsorship_raw)
        posting.locations = merged.locations
        posting.location_labels = merged.location_labels
        posting.is_remote = merged.is_remote
        posting.is_active = merged.is_active
        posting.posted_at = merged.posted_at
        posting.source_updated_at = merged.updated_at
        posting.last_seen_at = datetime.now(UTC)
        session.flush()

        _record_sources(session, posting, merged)
        report.created += int(is_new)
        report.updated += int(not is_new)

    report.merged_count = len(merged_postings)
    report.finished_at = datetime.now(UTC)
    return report


def _record_sources(session: Session, posting: Posting, merged: MergedPosting) -> None:
    """Attach provenance rows, one per source sighting.

    A raw upstream row is one sighting and belongs to exactly one posting,
    which is what ``uq_source_fingerprint`` enforces. The lookup is therefore
    global rather than per-posting: whenever dedup regroups a row onto a
    different canonical posting -- which happens any time matching improves --
    the existing sighting is re-pointed rather than inserted a second time.
    """
    if not merged.members:
        return

    keys = {(m.source_id, m.fingerprint) for m in merged.members}
    existing = {
        (s.source_id, s.source_fingerprint): s
        for s in session.scalars(
            select(PostingSource).where(
                tuple_(PostingSource.source_id, PostingSource.source_fingerprint).in_(keys)
            )
        )
    }

    for member in merged.members:
        sighting = existing.get((member.source_id, member.fingerprint))
        if sighting is None:
            session.add(
                PostingSource(
                    posting_id=posting.id,
                    source_id=member.source_id,
                    source_url=member.url,
                    source_fingerprint=member.fingerprint,
                    raw=member.raw,
                )
            )
        elif sighting.posting_id != posting.id:
            sighting.posting_id = posting.id
            sighting.source_url = member.url


def run_ingest(
    session: Session,
    *,
    max_tier: int = 2,
    today: date | None = None,
    connectors: list[Connector] | None = None,
) -> IngestReport:
    """Fetch every enabled source, dedup across them, and persist.

    Defaults to tiers 1-2, which is the fast path that already produces a
    complete usable list; higher tiers add breadth at the cost of time.
    """
    today = today or datetime.now(UTC).date()
    if connectors is None:
        connectors = connectors_by_tier(max_tier)
        if max_tier >= 3:
            # Tier 3 is per company, so its targets depend on what earlier
            # tiers have already surfaced.
            connectors = connectors + ats_connectors(session)

    all_rows: list[RawPosting] = []
    results: list[SourceResult] = []
    for connector in connectors:
        rows, result = fetch_source(connector, session)
        all_rows.extend(rows)
        results.append(result)
    session.flush()

    merged = deduplicate(all_rows)
    report = persist(session, merged, today)
    report.sources = results
    report.raw_count = len(all_rows)
    logger.info("ingest complete: %s | %s", report.summary(), dedup_stats(len(all_rows), merged))
    return report
