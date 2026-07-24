"""Tier 3: direct ATS job-board APIs.

These matter more than their row count suggests. Tiers 1-2 are curated lists of
*links* -- company, title, location, URL and nothing else -- so match scoring
against them is working from a job title alone, which is weak evidence and the
UI has to say so. The ATS boards are the only sources that carry the full job
description, which is what the keyword tailor and match scoring actually need.

All of these are public, unauthenticated JSON endpoints that vendors publish
specifically so companies can build their own careers pages. Using them is the
intended path, and it is far politer than scraping the rendered site.

Verified live: Greenhouse (Stripe, 525 roles), Ashby (OpenAI, 737),
SmartRecruiters, Lever, Workable, Recruitee.
"""

from __future__ import annotations

import html
import re
from abc import abstractmethod
from datetime import UTC, datetime

import httpx

from ..base import Connector, ConnectorError, RawPosting

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")

# Only campus-relevant roles are kept. These boards list every opening at the
# company, and a senior staff engineer role is noise for this operator.
_EARLY_CAREER_RE = re.compile(
    r"\b(intern(ship)?s?|co-?op|new\s*grad(uate)?|entry[\s-]*level|campus|"
    r"university|student|apprentice(ship)?|summer analyst|early career|"
    r"rotational|trainee|graduate (program|programme|scheme|analyst|engineer))\b",
    re.IGNORECASE,
)

# Senior signals that override a false positive from the pattern above (e.g.
# "Engineering Manager, University Recruiting" is not a student role).
_SENIOR_RE = re.compile(
    r"\b(senior|staff|principal|lead|manager|director|head of|vp|vice president|"
    r"architect|recruiter|recruiting)\b",
    re.IGNORECASE,
)


def is_early_career(title: str) -> bool:
    """Whether a title looks like a student or new-grad role."""
    if not title or not _EARLY_CAREER_RE.search(title):
        return False
    return not _SENIOR_RE.search(title)


def clean_html(raw: str | None) -> str | None:
    """Flatten an HTML job description to readable text.

    Descriptions arrive as HTML fragments. Structure is not needed -- the text
    analysis works on words -- but paragraph breaks are kept so the description
    stays readable when shown to the operator.
    """
    if not raw:
        return None

    # Unescape *before* stripping tags. Greenhouse returns entity-encoded
    # markup (``&lt;p&gt;``), so stripping first would leave the tags behind as
    # literal text once they were decoded. Twice, because some boards
    # double-encode.
    text = html.unescape(html.unescape(raw))

    text = re.sub(r"<\s*(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*li[^>]*>", "\n- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", " ", text, flags=re.I | re.S)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


def _iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class AtsConnector(Connector):
    """One company's board on one ATS vendor.

    Unlike the list repos, a failure here is routine and cheap: companies
    change board slugs and take boards down. The pipeline isolates each
    connector, so a dead board costs one company rather than the run.
    """

    tier = 3
    vendor: str = ""

    def __init__(self, slug: str, company_name: str | None = None) -> None:
        self.slug = slug
        self.company_name = company_name or slug.replace("-", " ").title()
        self.source_id = f"ats_{self.vendor}_{slug}"
        self.description = f"{self.company_name} ({self.vendor} board)"

    @property
    @abstractmethod
    def url(self) -> str: ...

    @abstractmethod
    def parse(self, payload: object) -> list[RawPosting]: ...

    def fetch(self, client: httpx.Client) -> list[RawPosting]:
        try:
            response = client.get(self.url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"{self.source_id}: fetch failed: {exc}") from exc
        except ValueError as exc:
            raise ConnectorError(f"{self.source_id}: invalid JSON: {exc}") from exc
        return [p for p in self.parse(payload) if p.is_valid()]

    def _posting(self, *, title: str, url: str, **kwargs) -> RawPosting:
        return RawPosting(
            source_id=self.source_id,
            company_name=self.company_name,
            title=title,
            url=url,
            employment_hint="internship" if "intern" in title.lower() else None,
            **kwargs,
        )


class GreenhouseConnector(AtsConnector):
    """``boards-api.greenhouse.io``. Returns every job in one response."""

    vendor = "greenhouse"

    @property
    def url(self) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{self.slug}/jobs?content=true"

    def parse(self, payload: object) -> list[RawPosting]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ConnectorError(f"{self.source_id}: unexpected payload shape")
        postings = []
        for job in payload["jobs"]:
            title = (job.get("title") or "").strip()
            url = (job.get("absolute_url") or "").strip()
            if not (title and url) or not is_early_career(title):
                continue
            location = ((job.get("location") or {}).get("name") or "").strip()
            postings.append(
                self._posting(
                    title=title,
                    url=url,
                    description=clean_html(job.get("content")),
                    locations_raw=[location] if location else [],
                    updated_at=_iso(job.get("updated_at")),
                    posted_at=_iso(job.get("first_published") or job.get("updated_at")),
                    raw={"greenhouse_id": job.get("id")},
                )
            )
        return postings


class AshbyConnector(AtsConnector):
    """``api.ashbyhq.com`` posting API."""

    vendor = "ashby"

    @property
    def url(self) -> str:
        return f"https://api.ashbyhq.com/posting-api/job-board/{self.slug}?includeCompensation=true"

    def parse(self, payload: object) -> list[RawPosting]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ConnectorError(f"{self.source_id}: unexpected payload shape")
        postings = []
        for job in payload["jobs"]:
            title = (job.get("title") or "").strip()
            url = (job.get("jobUrl") or job.get("applyUrl") or "").strip()
            if not (title and url) or not is_early_career(title):
                continue
            locations = [job.get("location")] + list(job.get("secondaryLocations") or [])
            postings.append(
                self._posting(
                    title=title,
                    url=url,
                    description=clean_html(job.get("descriptionHtml"))
                    or (job.get("descriptionPlain") or None),
                    locations_raw=[str(x) for x in locations if x],
                    posted_at=_iso(job.get("publishedAt")),
                    is_active=job.get("isListed", True),
                    raw={"ashby_id": job.get("id"), "department": job.get("department")},
                )
            )
        return postings


class LeverConnector(AtsConnector):
    """``api.lever.co`` v0 postings feed."""

    vendor = "lever"

    @property
    def url(self) -> str:
        return f"https://api.lever.co/v0/postings/{self.slug}?mode=json"

    def parse(self, payload: object) -> list[RawPosting]:
        if not isinstance(payload, list):
            raise ConnectorError(f"{self.source_id}: unexpected payload shape")
        postings = []
        for job in payload:
            if not isinstance(job, dict):
                continue
            title = (job.get("text") or "").strip()
            url = (job.get("hostedUrl") or job.get("applyUrl") or "").strip()
            if not (title and url) or not is_early_career(title):
                continue
            categories = job.get("categories") or {}
            created = job.get("createdAt")
            postings.append(
                self._posting(
                    title=title,
                    url=url,
                    description=job.get("descriptionPlain") or clean_html(job.get("description")),
                    locations_raw=[c for c in [categories.get("location")] if c],
                    posted_at=(
                        datetime.fromtimestamp(created / 1000, tz=UTC)
                        if isinstance(created, int | float) and created > 0
                        else None
                    ),
                    raw={"lever_id": job.get("id"), "team": categories.get("team")},
                )
            )
        return postings


class SmartRecruitersConnector(AtsConnector):
    """``api.smartrecruiters.com``. Paginated, and the list response carries no
    description -- so each kept posting needs a follow-up detail fetch."""

    vendor = "smartrecruiters"
    page_size = 100

    @property
    def url(self) -> str:
        return f"https://api.smartrecruiters.com/v1/companies/{self.slug}/postings"

    def parse(self, payload: object) -> list[RawPosting]:
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
            raise ConnectorError(f"{self.source_id}: unexpected payload shape")
        postings = []
        for job in payload["content"]:
            title = (job.get("name") or "").strip()
            job_id = job.get("id")
            if not (title and job_id) or not is_early_career(title):
                continue
            location = job.get("location") or {}
            label = ", ".join(str(x) for x in [location.get("city"), location.get("region")] if x)
            postings.append(
                self._posting(
                    title=title,
                    url=f"https://jobs.smartrecruiters.com/{self.slug}/{job_id}",
                    locations_raw=[label] if label else [],
                    posted_at=_iso(job.get("releasedDate")),
                    raw={"smartrecruiters_id": job_id},
                )
            )
        return postings

    def fetch(self, client: httpx.Client) -> list[RawPosting]:
        collected: list[RawPosting] = []
        offset = 0
        while True:
            try:
                response = client.get(self.url, params={"limit": self.page_size, "offset": offset})
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPError as exc:
                raise ConnectorError(f"{self.source_id}: fetch failed: {exc}") from exc
            except ValueError as exc:
                raise ConnectorError(f"{self.source_id}: invalid JSON: {exc}") from exc

            collected.extend(self.parse(payload))
            offset += self.page_size
            if offset >= int(payload.get("totalFound") or 0) or offset > 2000:
                break
        return [p for p in collected if p.is_valid()]


VENDORS: dict[str, type[AtsConnector]] = {
    "greenhouse": GreenhouseConnector,
    "ashby": AshbyConnector,
    "lever": LeverConnector,
    "smartrecruiters": SmartRecruitersConnector,
}


def build(vendor: str, slug: str, company_name: str | None = None) -> AtsConnector | None:
    """Construct a connector, or ``None`` for a vendor we do not support."""
    factory = VENDORS.get((vendor or "").lower())
    return factory(slug, company_name) if factory else None
