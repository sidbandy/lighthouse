"""Which company boards to poll directly.

Tier 3 is opt-in per company rather than a blanket crawl. Polling every board
we can detect would be thousands of requests for roles the operator will never
apply to; polling their actual targets is a few dozen and returns the full
descriptions that match scoring needs.

Two ways a company gets here:

* It is in the seed list below -- the firms that dominate a SWE/quant campus
  search, with slugs verified against the live boards.
* Its posting URLs already told us the vendor and slug during a Tier 1-2
  ingest, so we can enrich a company the operator cares about without anyone
  hand-maintaining an entry.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.models import Company, Posting
from .connectors.ats import VENDORS, AtsConnector, build

# (vendor, slug, display name). Verified against the live boards.
SEED_TARGETS: tuple[tuple[str, str, str], ...] = (
    # Quant and trading. These matter most right now: the Summer 2027 quant
    # cycle opens in August, ahead of everything else. Slugs verified live --
    # several are not the obvious guess ("drweng", not "drw").
    ("greenhouse", "janestreet", "Jane Street"),
    ("greenhouse", "optiverus", "Optiver"),
    ("greenhouse", "imc", "IMC Trading"),
    ("greenhouse", "drweng", "DRW"),
    ("greenhouse", "jumptrading", "Jump Trading"),
    ("greenhouse", "towerresearchcapital", "Tower Research Capital"),
    ("greenhouse", "akunacapital", "Akuna Capital"),
    # Infrastructure and platform companies with strong intern programmes.
    ("greenhouse", "stripe", "Stripe"),
    ("greenhouse", "databricks", "Databricks"),
    ("greenhouse", "figma", "Figma"),
    ("greenhouse", "cloudflare", "Cloudflare"),
    ("greenhouse", "datadog", "Datadog"),
    ("greenhouse", "robinhood", "Robinhood"),
    ("greenhouse", "coinbase", "Coinbase"),
    ("greenhouse", "airbnb", "Airbnb"),
    ("greenhouse", "doordashusa", "DoorDash"),
    ("greenhouse", "instacart", "Instacart"),
    ("greenhouse", "snowflake", "Snowflake"),
    ("greenhouse", "mongodb", "MongoDB"),
    ("greenhouse", "twosigma", "Two Sigma"),
    ("lever", "palantir", "Palantir"),
    ("ashby", "ramp", "Ramp"),
    ("ashby", "openai", "OpenAI"),
    ("ashby", "anthropic", "Anthropic"),
    ("ashby", "scale", "Scale AI"),
    ("ashby", "linear", "Linear"),
    ("ashby", "vercel", "Vercel"),
    ("ashby", "notion", "Notion"),
    # Mid-tier employers with real intern programmes. The seed list was
    # entirely elite and high-tier, which biased description coverage toward
    # exactly the companies hardest to get into -- and descriptions are what
    # match scoring runs on, so the postings the operator could best evaluate
    # were the ones they were least likely to get. Every slug below was hit
    # live and returned a board carrying student roles.
    ("greenhouse", "samsara", "Samsara"),
    ("greenhouse", "affirm", "Affirm"),
    ("greenhouse", "fanduel", "FanDuel"),
    ("greenhouse", "tripadvisor", "Tripadvisor"),
    ("greenhouse", "cargurus", "CarGurus"),
    ("greenhouse", "klaviyo", "Klaviyo"),
    ("greenhouse", "asana", "Asana"),
    ("greenhouse", "peloton", "Peloton"),
    ("greenhouse", "dropbox", "Dropbox"),
    ("greenhouse", "squarespace", "Squarespace"),
)

# Board slug as it appears in a posting URL, per vendor.
_SLUG_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("greenhouse", re.compile(r"(?:boards|job-boards)\.greenhouse\.io/([a-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([a-z0-9_-]+)", re.I)),
    ("smartrecruiters", re.compile(r"jobs\.smartrecruiters\.com/([a-z0-9_-]+)", re.I)),
)


def detect_board(url: str) -> tuple[str, str] | None:
    """Recover ``(vendor, slug)`` from a posting URL, if it is a known board.

    Many companies link through their own domain, in which case there is
    nothing to recover -- that is expected, not a failure.
    """
    if not url:
        return None
    for vendor, pattern in _SLUG_PATTERNS:
        if match := pattern.search(url):
            slug = match.group(1).lower()
            if slug not in {"embed", "job", "jobs"}:
                return vendor, slug
    return None


def discover_targets(
    session: Session, *, min_postings: int = 3, limit: int = 60
) -> list[tuple[str, str, str]]:
    """Find boards worth polling from postings already ingested.

    A company appearing repeatedly across the curated lists is one the operator
    is likely to care about, and its URLs usually reveal the board slug -- so
    enrichment needs no manual configuration.
    """
    rows = session.execute(
        select(Company.name, Posting.url, func.count(Posting.id).label("n"))
        .join(Posting, Posting.company_id == Company.id)
        .where(Posting.is_active.is_(True))
        .group_by(Company.name, Posting.url)
    ).all()

    found: dict[tuple[str, str], tuple[str, int]] = {}
    for company_name, url, count in rows:
        detected = detect_board(url)
        if detected is None:
            continue
        name, total = found.get(detected, (company_name, 0))
        found[detected] = (name, total + int(count))

    ranked = sorted(
        ((v, s, n, total) for (v, s), (n, total) in found.items() if total >= min_postings),
        key=lambda x: -x[3],
    )
    return [(vendor, slug, name) for vendor, slug, name, _ in ranked[:limit]]


def _dedupe(targets: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen: set[tuple[str, str]] = set()
    unique = []
    for vendor, slug, name in targets:
        key = (vendor.lower(), slug.lower())
        if key in seen or vendor.lower() not in VENDORS:
            continue
        seen.add(key)
        unique.append((vendor, slug, name))
    return unique


def ats_connectors(
    session: Session | None = None, *, include_discovered: bool = True, limit: int = 60
) -> list[AtsConnector]:
    """Every Tier 3 connector to run: the seed list plus anything discovered."""
    targets = list(SEED_TARGETS)
    if session is not None and include_discovered:
        targets += discover_targets(session, limit=limit)

    connectors = []
    for vendor, slug, name in _dedupe(targets):
        if (connector := build(vendor, slug, name)) is not None:
            connectors.append(connector)
    return connectors
