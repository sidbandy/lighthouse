"""Tier 1: Simplify's structured listings feed.

The single most valuable source. Simplify publishes ``listings.json`` alongside
the human-readable README, which means no markdown parsing and -- crucially --
a real ``terms`` array covering every cycle from Summer 2026 through Fall 2028.
That field is what makes off-cycle coverage possible at all; the rendered
README only shows one season.

Two repos share the schema exactly: the internship list and the new-grad list.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ..base import Connector, ConnectorError, RawPosting

_RAW_BASE = "https://raw.githubusercontent.com"


def _timestamp(value: object) -> datetime | None:
    """Simplify stores epoch seconds; tolerate nulls and junk."""
    if not isinstance(value, int | float) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


class SimplifyListingsConnector(Connector):
    """Reads a Simplify-format ``listings.json``.

    Rows carry ``is_visible`` (whether Simplify shows it) separately from
    ``active`` (whether the role is open). We keep only visible rows and let
    ``active`` flow through, so closed postings can still be displayed and
    filtered rather than silently vanishing.
    """

    tier = 1

    def __init__(
        self,
        source_id: str,
        repo: str,
        branch: str = "dev",
        path: str = ".github/scripts/listings.json",
        employment_hint: str = "internship",
        description: str = "",
    ) -> None:
        self.source_id = source_id
        self.repo = repo
        self.branch = branch
        self.path = path
        self.employment_hint = employment_hint
        self.description = description or repo

    @property
    def url(self) -> str:
        return f"{_RAW_BASE}/{self.repo}/{self.branch}/{self.path}"

    def fetch(self, client: httpx.Client) -> list[RawPosting]:
        try:
            response = client.get(self.url)
            response.raise_for_status()
            rows = response.json()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"{self.source_id}: fetch failed: {exc}") from exc
        except ValueError as exc:
            raise ConnectorError(f"{self.source_id}: response was not valid JSON: {exc}") from exc

        if not isinstance(rows, list):
            raise ConnectorError(
                f"{self.source_id}: expected a JSON array, got {type(rows).__name__}"
            )

        return [posting for row in rows if (posting := self._to_posting(row))]

    def _to_posting(self, row: object) -> RawPosting | None:
        if not isinstance(row, dict):
            return None
        if row.get("is_visible") is False:
            return None

        url = (row.get("url") or "").strip()
        company = (row.get("company_name") or "").strip()
        title = (row.get("title") or "").strip()
        if not (url and company and title):
            return None

        locations = row.get("locations")
        terms = row.get("terms")

        posting = RawPosting(
            source_id=self.source_id,
            company_name=company,
            title=title,
            url=url,
            locations_raw=[str(x) for x in locations] if isinstance(locations, list) else [],
            explicit_terms=[str(x) for x in terms] if isinstance(terms, list) else [],
            sponsorship_raw=row.get("sponsorship"),
            employment_hint=self.employment_hint,
            posted_at=_timestamp(row.get("date_posted")),
            updated_at=_timestamp(row.get("date_updated")),
            is_active=bool(row.get("active", True)),
            raw={
                "id": row.get("id"),
                "category": row.get("category"),
                "source": row.get("source"),
                "company_url": row.get("company_url"),
                "degrees": row.get("degrees"),
            },
        )
        return posting if posting.is_valid() else None


def simplify_internships() -> SimplifyListingsConnector:
    """Summer + off-season internships. ~14.8k rows, all cycles."""
    return SimplifyListingsConnector(
        source_id="simplify_internships",
        repo="SimplifyJobs/Summer2026-Internships",
        employment_hint="internship",
        description="Simplify / Pitt CSC internship listings (structured JSON, all terms)",
    )


def simplify_new_grad() -> SimplifyListingsConnector:
    """Full-time new-grad roles, same schema."""
    return SimplifyListingsConnector(
        source_id="simplify_new_grad",
        repo="SimplifyJobs/New-Grad-Positions",
        employment_hint="new_grad",
        description="Simplify new-grad full-time listings (structured JSON)",
    )
