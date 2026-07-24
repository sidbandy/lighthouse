"""Tier 2: the curated GitHub list repos.

These are the community-maintained tables (vansh, speedyapply, zapplyjobs,
jobright, sndsh). They are the fastest-moving human-curated source and they
cover off-cycle roles the structured feeds sometimes miss, so they are worth
the parsing effort.

Two details do real damage if handled naively:

* ``↳`` in the Company column means "same company as above". It is used heavily
  -- consecutive roles at one firm are collapsed this way -- so the company has
  to be carried forward or attribution is lost on a large share of rows.
* Dates are written ``Jul 09`` with **no year**. Read literally, every posting
  from last December looks like it is from this December. The year is inferred
  by assuming a date cannot be in the future.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import httpx

from ..base import Connector, ConnectorError, RawPosting
from ..table_parser import (
    CITIZENSHIP_MARKERS,
    CLOSED_MARKERS,
    NO_SPONSORSHIP_MARKERS,
    clean_cell,
    is_continuation,
    parse_tables,
    split_multi,
)

_RAW_BASE = "https://raw.githubusercontent.com"

# Header aliases across repos, mapped onto the fields we need.
_COMPANY_KEYS = ("company", "company_name", "name", "employer")
_ROLE_KEYS = ("role", "position", "title", "job_title", "role_title")
_LOCATION_KEYS = ("location", "locations", "location_s", "city")
_LINK_KEYS = ("application_link", "apply", "link", "application", "posting", "apply_link", "url")
_DATE_KEYS = ("date_posted", "date", "age", "posted", "date_added")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip

_DATE_RE = re.compile(r"\b([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})\b")
_ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_AGE_RE = re.compile(r"\b(\d+)\s*(d|day|days|h|hr|hour|hours|mo|month|months)\b", re.IGNORECASE)


def _first_key(row_keys: list[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in row_keys:
            return candidate
    # Fall back to a substring match for headers like "application/link".
    for key in row_keys:
        if any(candidate in key for candidate in candidates):
            return key
    return None


def parse_posted_date(value: str, *, today: date) -> datetime | None:
    """Parse the date column, inferring the year when it is omitted.

    ``"Jul 09"`` on 2026-07-24 is 2026; ``"Dec 15"`` is 2025, because a posting
    cannot have been made in the future.
    """
    text = (value or "").strip()
    if not text:
        return None

    if match := _ISO_RE.search(text):
        year, month, day = (int(g) for g in match.groups())
        try:
            return datetime(year, month, day, tzinfo=UTC)
        except ValueError:
            return None

    if match := _AGE_RE.search(text):
        amount, unit = int(match.group(1)), match.group(2).lower()
        days = amount * (30 if unit.startswith("mo") else 1 if unit.startswith("d") else 0)
        if unit.startswith("h"):
            days = 0
        try:
            resolved = date.fromordinal(today.toordinal() - days)
        except ValueError:
            return None
        return datetime(resolved.year, resolved.month, resolved.day, tzinfo=UTC)

    if match := _DATE_RE.search(text):
        month = _MONTHS.get(match.group(1).lower())
        if not month:
            return None
        day = int(match.group(2))
        year = today.year if (month, day) <= (today.month, today.day) else today.year - 1
        try:
            return datetime(year, month, day, tzinfo=UTC)
        except ValueError:
            return None
    return None


@dataclass
class MarkdownRepoConnector(Connector):
    """Parses one markdown table file from a GitHub repo.

    Registry-driven: adding another list repo is a config entry, not new code.
    """

    source_id: str
    repo: str
    branch: str = "main"
    path: str = "README.md"
    employment_hint: str = "internship"
    description: str = ""
    tier: int = 2
    # Rows whose company or role is missing after cleaning are dropped; a table
    # yielding almost nothing usually means the file's structure changed.
    min_expected_rows: int = 5
    default_terms: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{_RAW_BASE}/{self.repo}/{self.branch}/{self.path}"

    def fetch(self, client: httpx.Client) -> list[RawPosting]:
        try:
            response = client.get(self.url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"{self.source_id}: fetch failed: {exc}") from exc

        parsed = parse_tables(response.text)
        if not parsed.rows:
            raise ConnectorError(f"{self.source_id}: no table rows found (layout may have changed)")

        today = datetime.now(UTC).date()
        keys = list(parsed.rows[0].cells)
        company_key = _first_key(keys, _COMPANY_KEYS)
        role_key = _first_key(keys, _ROLE_KEYS)
        if not company_key or not role_key:
            raise ConnectorError(
                f"{self.source_id}: could not locate company/role columns in {keys}"
            )
        location_key = _first_key(keys, _LOCATION_KEYS)
        link_key = _first_key(keys, _LINK_KEYS)
        date_key = _first_key(keys, _DATE_KEYS)

        postings: list[RawPosting] = []
        last_company = ""

        for row in parsed.rows:
            company_cell = row.get(company_key)
            if is_continuation(company_cell):
                company = last_company
            else:
                company = clean_cell(company_cell, keep_markers=False)
                if company:
                    last_company = company
            if not company:
                continue

            role_cell = row.get(role_key)
            title = clean_cell(role_cell, keep_markers=False)
            if not title:
                continue

            url = self._resolve_url(row, link_key, role_key, company_key)
            if not url:
                continue

            flags = f"{company_cell}{role_cell}{row.get(location_key) if location_key else ''}"
            locations = (
                split_multi(clean_cell(row.get(location_key), keep_markers=False))
                if location_key
                else []
            )
            posted_at = (
                parse_posted_date(clean_cell(row.get(date_key)), today=today) if date_key else None
            )

            posting = RawPosting(
                source_id=self.source_id,
                company_name=company,
                title=title,
                url=url,
                locations_raw=locations,
                explicit_terms=list(self.default_terms),
                sponsorship_raw=self._sponsorship(flags),
                employment_hint=self.employment_hint,
                posted_at=posted_at,
                is_active=not any(marker in flags for marker in CLOSED_MARKERS),
                raw={"repo": self.repo, "path": self.path},
            )
            if posting.is_valid():
                postings.append(posting)

        if len(postings) < self.min_expected_rows:
            raise ConnectorError(
                f"{self.source_id}: only {len(postings)} usable rows from "
                f"{len(parsed.rows)} parsed (layout may have changed)"
            )
        return postings

    @staticmethod
    def _resolve_url(row, link_key: str | None, role_key: str, company_key: str) -> str | None:
        """The apply URL, wherever this repo happens to put it."""
        for key in (link_key, role_key, company_key):
            if key and (url := row.first_link(key)):
                return url
        for values in row.links.values():
            if values:
                return values[0]
        return None

    @staticmethod
    def _sponsorship(flags: str) -> str | None:
        if any(marker in flags for marker in CITIZENSHIP_MARKERS):
            return "U.S. Citizenship is Required"
        if any(marker in flags for marker in NO_SPONSORSHIP_MARKERS):
            return "Does Not Offer Sponsorship"
        return None
