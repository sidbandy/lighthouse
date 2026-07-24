"""The connector contract.

Every source -- structured JSON, hand-edited markdown, a live ATS API --
produces the same :class:`RawPosting`. Everything downstream (term resolution,
dedup, persistence) is then source-agnostic, which is what keeps adding a feed
cheap.

Connectors are also *independently failable*. A connector that raises is
quarantined for that run and the rest carry on; one rotted source must never
take the list down.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from ..core.config import get_settings
from .normalize import (
    canonical_company,
    canonical_url,
    extract_ats,
    extract_job_id,
    location_label,
    normalize_title,
    parse_location,
)


@dataclass(slots=True)
class RawPosting:
    """One posting as a connector saw it, before dedup.

    ``fingerprint`` is a hash of the upstream content, so re-ingesting an
    unchanged row is a no-op and a run can be diffed against the last one to
    find genuinely new postings.
    """

    source_id: str
    company_name: str
    title: str
    url: str

    description: str | None = None
    locations_raw: list[str] = field(default_factory=list)
    explicit_terms: list[str] = field(default_factory=list)
    sponsorship_raw: str | None = None
    employment_hint: str | None = None
    posted_at: datetime | None = None
    updated_at: datetime | None = None
    is_active: bool = True
    raw: dict = field(default_factory=dict)

    # Derived in __post_init__; kept on the object so dedup never recomputes.
    canonical_company_name: str = field(init=False, default="")
    normalized_title_value: str = field(init=False, default="")
    canonical_url_value: str = field(init=False, default="")
    ats_vendor: str | None = field(init=False, default=None)
    ats_job_id: str | None = field(init=False, default=None)
    locations: list[dict] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.company_name = (self.company_name or "").strip()
        self.title = (self.title or "").strip()
        self.canonical_company_name = canonical_company(self.company_name)
        self.normalized_title_value = normalize_title(self.title)
        self.canonical_url_value = canonical_url(self.url)
        self.ats_vendor = extract_ats(self.url)
        self.ats_job_id = extract_job_id(self.url)
        self.locations = [parse_location(loc) for loc in self.locations_raw if loc and loc.strip()]

    @property
    def location_labels(self) -> list[str]:
        return sorted({label for loc in self.locations if (label := location_label(loc))})

    @property
    def is_remote(self) -> bool:
        return any(loc.get("is_remote") for loc in self.locations)

    @property
    def has_description(self) -> bool:
        return bool(self.description and self.description.strip())

    @property
    def fingerprint(self) -> str:
        """Stable hash of the fields that would make this a different posting."""
        payload = json.dumps(
            {
                "s": self.source_id,
                "c": self.canonical_company_name,
                "t": self.normalized_title_value,
                "u": self.canonical_url_value,
                "l": sorted(self.locations_raw),
                "terms": sorted(self.explicit_terms),
                "active": self.is_active,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def is_valid(self) -> bool:
        """Rows missing a company, title or URL are unusable, not merely poor."""
        return bool(self.canonical_company_name and self.title and self.canonical_url_value)


class ConnectorError(RuntimeError):
    """Raised when a source cannot be ingested this run."""


class Connector(ABC):
    """Base class for every source.

    Subclasses implement :meth:`fetch`. ``tier`` is informational and mirrors
    the source catalogue: 1 = structured JSON, 2 = curated markdown repos,
    3 = direct ATS APIs, 4 = broad aggregators, 5 = optional keyed feeds.
    """

    source_id: str
    tier: int = 2
    description: str = ""

    @abstractmethod
    def fetch(self, client: httpx.Client) -> list[RawPosting]:
        """Return every posting this source currently lists."""

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{type(self).__name__} {self.source_id}>"


def build_client(**kwargs) -> httpx.Client:
    """HTTP client identifying itself politely to source hosts."""
    settings = get_settings()
    return httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        **kwargs,
    )
