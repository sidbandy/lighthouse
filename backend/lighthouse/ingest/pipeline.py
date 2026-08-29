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
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import bindparam as sa_bindparam
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..core.models import Company, OperatorTarget, Posting, PostingSource, SourceHealth
from .ats_targets import ats_connectors
from .base import Connector, RawPosting, build_client
from .dedup import MergedPosting, dedup_stats, deduplicate
from .normalize import (
    canonical_company,
    classify_employment_type,
    classify_role_family,
    parse_sponsorship,
)
from .registry import connectors_by_tier
from .seasons import is_applyable
from .terms import resolve_term

logger = logging.getLogger(__name__)

# How many rows go into one INSERT. Large enough that the round trips stop
# mattering, small enough to stay well inside Postgres' 65535 bind-parameter
# limit: a posting row binds ~25 columns, so 500 rows is ~12.5k parameters.
WRITE_CHUNK = 500

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
    # Two merged postings claiming one canonical URL. Always a dedup bug, so it
    # is counted and reported rather than quietly absorbed by the upsert.
    collapsed_in_batch: int = 0
    term_rules: dict[str, int] = field(default_factory=dict)

    @property
    def failed_sources(self) -> list[SourceResult]:
        return [s for s in self.sources if not s.ok]

    def summary(self) -> str:
        ok = sum(1 for s in self.sources if s.ok)
        line = (
            f"{ok}/{len(self.sources)} sources ok; {self.raw_count} raw -> "
            f"{self.merged_count} deduped; {self.created} new, {self.updated} updated"
        )
        # Only ever non-zero when dedup let two postings claim one canonical
        # URL, so it stays out of the line entirely rather than reading as a
        # normal statistic that happens to be zero.
        if self.collapsed_in_batch:
            line += f"; {self.collapsed_in_batch} collapsed (dedup let duplicates through)"
        return line


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


def reconcile_companies(session: Session) -> int:
    """Re-key company rows whose stored canonical name is out of date.

    ``canonical_company`` grows: an alias gets added, an initialism stops being
    split. Rows written under the old key would otherwise sit beside rows
    written under the new one — "IMC" and "IMC Trading" as two companies, each
    with half the postings, each able to miss a selectivity tier. Since the key
    is derived from the display name, the drift is detectable, so this recomputes
    every key and merges the collisions.

    Idempotent and cheap: one query, and it writes only when something actually
    moved. Returns the number of rows merged away.
    """
    companies = list(session.scalars(select(Company)))
    by_key = {c.canonical_name: c for c in companies}
    merged_away = 0

    for company in companies:
        current = canonical_company(company.name)
        if current == company.canonical_name:
            continue

        winner = by_key.get(current)
        if winner is None or winner is company:
            by_key.pop(company.canonical_name, None)
            company.canonical_name = current
            by_key[current] = company
            continue

        # Two rows for one company. Keep the one already under the right key and
        # move everything across; the ATS details are worth carrying over
        # because either row may be the one that was seeded with them.
        session.execute(
            update(Posting).where(Posting.company_id == company.id).values(company_id=winner.id)
        )
        session.execute(
            update(OperatorTarget)
            .where(OperatorTarget.company_id == company.id)
            .values(company_id=winner.id)
        )
        winner.ats_vendor = winner.ats_vendor or company.ats_vendor
        winner.ats_slug = winner.ats_slug or company.ats_slug
        winner.careers_url = winner.careers_url or company.careers_url
        winner.tier = winner.tier or company.tier
        by_key.pop(company.canonical_name, None)
        session.delete(company)
        merged_away += 1

    if merged_away or any(c.canonical_name != canonical_company(c.name) for c in companies):
        session.flush()
    return merged_away


def _chunks(rows: list, size: int = WRITE_CHUNK):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _resolve_companies(
    session: Session, merged_postings: list[MergedPosting]
) -> dict[str, uuid.UUID]:
    """Map every canonical company name in the batch to a company id.

    One SELECT for the whole batch and one INSERT for the ones that are new,
    rather than a lookup per posting. Names repeat heavily -- 23k postings come
    from ~4.8k companies -- so this collapses by roughly five to one before it
    touches the database at all.
    """
    wanted: dict[str, MergedPosting] = {}
    for merged in merged_postings:
        wanted.setdefault(merged.primary.canonical_company_name, merged)
    if not wanted:
        return {}

    ids: dict[str, uuid.UUID] = {}
    vendors: dict[str, str | None] = {}
    for chunk in _chunks(list(wanted), WRITE_CHUNK):
        for company_id, canonical, vendor in session.execute(
            select(Company.id, Company.canonical_name, Company.ats_vendor).where(
                Company.canonical_name.in_(chunk)
            )
        ):
            ids[canonical] = company_id
            vendors[canonical] = vendor

    new_rows = [
        {
            "name": merged.company_name,
            "canonical_name": key,
            "ats_vendor": merged.ats_vendor,
        }
        for key, merged in wanted.items()
        if key not in ids
    ]
    for chunk in _chunks(new_rows, WRITE_CHUNK):
        for company_id, canonical in session.execute(
            pg_insert(Company)
            .values(chunk)
            .on_conflict_do_nothing(index_elements=["canonical_name"])
            .returning(Company.id, Company.canonical_name)
        ):
            ids[canonical] = company_id

    # A concurrent run could have inserted a name between the SELECT and the
    # INSERT, in which case ON CONFLICT DO NOTHING returns nothing for it.
    missing = [key for key in wanted if key not in ids]
    if missing:
        for chunk in _chunks(missing, WRITE_CHUNK):
            for company_id, canonical in session.execute(
                select(Company.id, Company.canonical_name).where(
                    Company.canonical_name.in_(chunk)
                )
            ):
                ids[canonical] = company_id

    # Backfill a vendor onto a company first seen without one. Only where it is
    # currently null, so a known vendor is never overwritten by a feed that
    # happens not to carry it.
    # Only companies that already existed: one inserted a moment ago carried
    # its vendor in. `vendors` holds a key only for rows read by the SELECT,
    # which is exactly that set.
    backfill = [
        {"b_id": ids[key], "b_vendor": merged.ats_vendor}
        for key, merged in wanted.items()
        if merged.ats_vendor and key in vendors and not vendors[key]
    ]
    companies = Company.__table__
    for chunk in _chunks(backfill, WRITE_CHUNK):
        # Core table, not the ORM entity: an executemany against the entity is
        # read as a bulk update by primary key, which these rows are not.
        session.execute(
            update(companies)
            .where(companies.c.id == sa_bindparam("b_id"), companies.c.ats_vendor.is_(None))
            .values(ats_vendor=sa_bindparam("b_vendor")),
            chunk,
        )

    return ids


def _posting_row(
    merged: MergedPosting, resolution, company_id: uuid.UUID, seen_at: datetime
) -> dict:
    """One posting as a plain dict, ready for a bulk upsert."""
    return {
        "company_id": company_id,
        "title": merged.title,
        "normalized_title": merged.primary.normalized_title_value,
        "url": merged.url,
        "canonical_url": merged.canonical_url,
        "ats_job_id": merged.ats_job_id,
        "description": merged.description,
        "description_available": merged.description is not None,
        "season": resolution.cycle.season if resolution.cycle else None,
        "term_year": resolution.cycle.year if resolution.cycle else None,
        "term_rule": resolution.rule,
        "term_evidence": resolution.evidence,
        "employment_type": classify_employment_type(merged.title, merged.employment_hint),
        # Store the plain value (lowercase); role_family is a string column now.
        "role_family": classify_role_family(merged.title).value,
        "sponsorship": parse_sponsorship(merged.sponsorship_raw),
        "locations": merged.locations,
        "location_labels": merged.location_labels,
        "is_remote": merged.is_remote,
        "is_active": merged.is_active,
        "posted_at": merged.posted_at,
        "source_updated_at": merged.updated_at,
        "last_seen_at": seen_at,
    }


# Every column the upsert refreshes on an existing row. `canonical_url` is the
# arbiter and `company_id` is deliberately included: a posting can move between
# companies when name resolution improves.
_POSTING_UPDATE_COLUMNS = (
    "company_id",
    "title",
    "normalized_title",
    "url",
    "ats_job_id",
    "description",
    "description_available",
    "season",
    "term_year",
    "term_rule",
    "term_evidence",
    "employment_type",
    "role_family",
    "sponsorship",
    "locations",
    "location_labels",
    "is_remote",
    "is_active",
    "posted_at",
    "source_updated_at",
    "last_seen_at",
)


def _upsert_postings(session: Session, rows: list[dict]) -> dict[str, uuid.UUID]:
    """Bulk upsert on canonical_url, returning the id for every row written."""
    ids: dict[str, uuid.UUID] = {}
    for chunk in _chunks(rows, WRITE_CHUNK):
        statement = pg_insert(Posting).values(chunk)
        statement = statement.on_conflict_do_update(
            index_elements=["canonical_url"],
            set_={name: statement.excluded[name] for name in _POSTING_UPDATE_COLUMNS},
        ).returning(Posting.id, Posting.canonical_url)
        for posting_id, canonical_url in session.execute(statement):
            ids[canonical_url] = posting_id
    return ids


def _record_all_sources(
    session: Session,
    merged_postings: list[MergedPosting],
    posting_ids: dict[str, uuid.UUID],
) -> None:
    """Attach provenance rows for the whole batch, one per source sighting.

    A raw upstream row is one sighting and belongs to exactly one posting,
    which is what ``uq_source_fingerprint`` enforces. That constraint is also
    what makes this a single upsert: whenever dedup regroups a row onto a
    different canonical posting -- which happens any time matching improves --
    the conflict branch re-points the existing sighting rather than inserting a
    second one.

    ``raw`` is intentionally not refreshed on conflict. It is the payload as
    first seen, and the row is unchanged by definition when the fingerprint
    matches.
    """
    rows: dict[tuple[str, str], dict] = {}
    for merged in merged_postings:
        posting_id = posting_ids.get(merged.canonical_url)
        if posting_id is None:
            continue
        for member in merged.members:
            # Last writer wins within a batch. Two merged postings claiming one
            # sighting would be a dedup bug, and Postgres rejects a statement
            # that touches the same conflict target twice, so collapse here.
            rows[(member.source_id, member.fingerprint)] = {
                "posting_id": posting_id,
                "source_id": member.source_id,
                "source_url": member.url,
                "source_fingerprint": member.fingerprint,
                "raw": member.raw,
            }

    for chunk in _chunks(list(rows.values()), WRITE_CHUNK):
        statement = pg_insert(PostingSource).values(chunk)
        session.execute(
            statement.on_conflict_do_update(
                constraint="uq_source_fingerprint",
                set_={
                    "posting_id": statement.excluded.posting_id,
                    "source_url": statement.excluded.source_url,
                },
            )
        )


def persist(session: Session, merged_postings: list[MergedPosting], today: date) -> IngestReport:
    """Upsert deduplicated postings, keyed on canonical URL.

    Written in phases rather than a loop because the loop cost four statements
    per posting -- a company lookup, a posting SELECT, a flush, and a sightings
    SELECT. At 23k postings that is ~98k round trips, which is fine locally and
    took over twenty minutes against a network database, against a thirty
    minute CI timeout. The phases below issue a bounded number of statements
    regardless of batch size.
    """
    report = IngestReport(started_at=datetime.now(UTC))

    # Phase 1: resolve terms and drop cycles that have already started. Pure,
    # no database, so the filtering is done before anything is written.
    resolved: list[tuple[MergedPosting, object]] = []
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
        resolved.append((merged, resolution))

    report.merged_count = len(merged_postings)
    if not resolved:
        report.finished_at = datetime.now(UTC)
        return report

    # Phase 2: one company id per distinct name in the batch.
    company_ids = _resolve_companies(session, [m for m, _ in resolved])

    # Phase 3: which canonical URLs already exist, so created and updated stay
    # accurate. Read before the upsert, because afterwards every row exists.
    urls = [m.canonical_url for m, _ in resolved]
    known: set[str] = set()
    for chunk in _chunks(urls, WRITE_CHUNK):
        known.update(
            session.scalars(
                select(Posting.canonical_url).where(Posting.canonical_url.in_(chunk))
            )
        )

    seen_at = datetime.now(UTC)
    rows: dict[str, dict] = {}
    for merged, resolution in resolved:
        # Deduplicate within the batch: Postgres refuses a statement whose
        # ON CONFLICT target is hit twice. Dedup should have prevented this,
        # so it is counted rather than silently absorbed.
        if merged.canonical_url in rows:
            report.collapsed_in_batch += 1
        rows[merged.canonical_url] = _posting_row(
            merged, resolution, company_ids[merged.primary.canonical_company_name], seen_at
        )

    report.created = sum(1 for url in rows if url not in known)
    report.updated = len(rows) - report.created

    # Phase 4 and 5: write the postings, then their provenance.
    posting_ids = _upsert_postings(session, list(rows.values()))
    _record_all_sources(session, [m for m, _ in resolved], posting_ids)

    report.finished_at = datetime.now(UTC)
    return report


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
    # Before anything is written, bring existing company rows up to the current
    # normalisation so this run does not add a second row for a company that is
    # already here under an older key.
    reconcile_companies(session)
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
