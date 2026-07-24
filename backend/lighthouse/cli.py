"""Command-line interface.

Enough to run and inspect Lighthouse without the web UI, which matters while
the frontend is still being built and for scheduled runs.

    python -m lighthouse.cli ingest
    python -m lighthouse.cli postings --season summer --year 2027
    python -m lighthouse.cli sources
    python -m lighthouse.cli cycles
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime

from .core.db import session_scope
from .core.models import Season
from .discover import service
from .ingest.pipeline import run_ingest
from .ingest.registry import all_connectors
from .ingest.seasons import applyable_cycles

# Column widths chosen so a default 100-column terminal does not wrap.
_COMPANY_W = 24
_TITLE_W = 44


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def cmd_ingest(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with session_scope() as session:
        report = run_ingest(session, max_tier=args.max_tier, today=args.today)

    print(f"\n{report.summary()}")
    print(f"skipped (cycle already started): {report.skipped_not_applyable}")

    print("\nterm resolution:")
    for rule, count in sorted(report.term_rules.items(), key=lambda kv: -kv[1]):
        print(f"  {rule:22} {count:6}")

    print("\nsources:")
    for result in report.sources:
        status = "ok  " if result.ok else ("QUAR" if result.quarantined else "FAIL")
        line = f"  {status} {result.source_id:28} {result.row_count:6}"
        if result.error:
            line += f"  {result.error[:60]}"
        print(line)

    return 1 if report.failed_sources else 0


def cmd_postings(args: argparse.Namespace) -> int:
    filters = service.PostingFilters(
        seasons=[Season(args.season)] if args.season else [],
        term_years=[args.year] if args.year else [],
        role_families=[args.role] if args.role else [],
        states=args.state or [],
        search=args.search,
        remote_only=args.remote,
        with_description_only=args.described,
        limit=args.limit,
    )
    with session_scope() as session:
        items, total = service.list_postings(session, filters, args.today)

    print(f"{total} matching posting(s); showing {len(items)}\n")
    for item in items:
        term = item.term_label or "term unknown"
        locations = ", ".join(item.location_labels[:2]) or "-"
        age = f"{item.age_days}d" if item.age_days is not None else "  -"
        print(
            f"  {item.company_name[:_COMPANY_W]:{_COMPANY_W}} "
            f"{item.title[:_TITLE_W]:{_TITLE_W}} "
            f"{term:14} {age:>4}  {item.source_count}src  {locations[:28]}"
        )
    return 0


def cmd_cycles(args: argparse.Namespace) -> int:
    today = args.today or date.today()
    with session_scope() as session:
        counts = {c.term_label: c.count for c in service.cycle_counts(session, today)}

    print(f"Cycles still open to apply to as of {today}:\n")
    for cycle in applyable_cycles(today):
        print(
            f"  {cycle.label:14} starts {cycle.start_date}  "
            f"{counts.get(cycle.label, 0):5} active postings"
        )
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    with session_scope() as session:
        health = {h.source_id: h for h in service.source_health(session)}
        live = service.source_breakdown(session)

    print(f"{'source':30} {'tier':>4} {'live':>7} {'last ok':>12}  status")
    for connector in sorted(all_connectors(), key=lambda c: (c.tier, c.source_id)):
        record = health.get(connector.source_id)
        last_ok = (
            record.last_success_at.date().isoformat()
            if record and record.last_success_at
            else "never"
        )
        if record is None:
            status = "not yet run"
        elif record.is_quarantined:
            status = f"QUARANTINED: {(record.last_error or '')[:40]}"
        elif record.last_error:
            status = f"error: {record.last_error[:40]}"
        else:
            status = "ok"
        print(
            f"{connector.source_id:30} {connector.tier:>4} "
            f"{live.get(connector.source_id, 0):>7} {last_ok:>12}  {status}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lighthouse", description=__doc__)
    parser.add_argument(
        "--today", type=_parse_date, default=None, help="Override today's date (YYYY-MM-DD)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Fetch every source and refresh the posting list.")
    ingest.add_argument(
        "--max-tier",
        type=int,
        default=2,
        choices=[1, 2, 3, 4, 5],
        help="Tiers 1-2 are the fast path and already give a complete list.",
    )
    ingest.set_defaults(func=cmd_ingest)

    postings = sub.add_parser("postings", help="List postings.")
    postings.add_argument("--season", choices=[s.value for s in Season])
    postings.add_argument("--year", type=int)
    postings.add_argument("--role", help="Role family, e.g. swe, quant, ai_ml.")
    postings.add_argument("--state", action="append", help="Two-letter state code; repeatable.")
    postings.add_argument("--search")
    postings.add_argument("--remote", action="store_true")
    postings.add_argument(
        "--described", action="store_true", help="Only postings carrying a full description."
    )
    postings.add_argument("--limit", type=int, default=25)
    postings.set_defaults(func=cmd_postings)

    cycles = sub.add_parser("cycles", help="Show cycles still open to apply to.")
    cycles.set_defaults(func=cmd_cycles)

    sources = sub.add_parser("sources", help="Show every source and its health.")
    sources.set_defaults(func=cmd_sources)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
