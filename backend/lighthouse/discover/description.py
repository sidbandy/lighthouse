"""Fetching one posting's description, on demand.

Most of the market reaches Lighthouse as a title and a link. The GitHub list
repos that give the widest coverage carry no description at all, so roughly
19 in 20 active postings are title-only -- which is why the Target lane, the
one that needs a real description before it will call a match realistic, stays
close to empty while Reach fills up.

The bulk fix is a Workday connector and tier-4 aggregators, and that is a real
piece of work. This is the small one that covers the case actually in front of
the operator: they have opened a posting and are deciding whether to spend
forty minutes on it. Fetching that single page, now, is cheap and is a thing
they already asked for by opening it.

The rules this follows, in order of how much they matter:

* **One posting, on an action the operator already took.** Never a bulk crawl,
  never speculative, never in the background.
* **``robots.txt`` decides.** Checked per host and cached for the process. A
  disallow is a refusal, reported as one, not routed around.
* **Never invent a description.** A page that yields boilerplate, a login wall
  or three words of nav produces "nothing readable", not a short description.
  A wrong description is worse than none: it feeds match scoring, the tailor
  and the brief, and the operator would never know it was junk.
"""

from __future__ import annotations

import logging
import re
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import httpx
from sqlalchemy.orm import Session

from ..core.models import Posting
from ..ingest.base import build_client
from ..ingest.connectors.ats import clean_html
from . import ranking

logger = logging.getLogger(__name__)

# Below this a "description" is a nav bar, a cookie banner or a login wall.
# Real postings run to thousands of characters; the shortest genuine ones seen
# in the corpus are still several hundred.
MIN_USEFUL_CHARS = 400

# Above this it is a page, not a posting. Measured against the real thing: a
# Lever `/apply` page flattens to 109,000 characters, roughly 90% of it the
# university dropdown -- several thousand school names that would go into match
# scoring as though the employer had asked for them. The longest genuine
# descriptions in the corpus are well under this.
MAX_USEFUL_CHARS = 40_000

# Pages larger than this are not job descriptions, they are applications. Read
# far enough to find the text and stop.
MAX_BYTES = 2_000_000

# Page furniture, removed before flattening. The application form matters most:
# it is where the dropdowns live. `clean_html` already handles script and style
# for the ATS payloads, but those arrive as description fragments -- a whole
# page needs more taken off it.
_FURNITURE = re.compile(
    r"<\s*(script|style|select|form|nav|footer|header|svg|noscript)[^>]*>.*?"
    r"<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Lever and Greenhouse both serve the application form at `/apply`, which is
# the form and not the posting. The description lives at the base URL.
_APPLY_SUFFIX = re.compile(r"/apply/?$", re.IGNORECASE)

# Cached per process. Hosts do not change their robots.txt during a session,
# and re-fetching it per posting would be the rude thing this check exists to
# avoid.
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


@dataclass(slots=True, frozen=True)
class FetchResult:
    """What happened, in words the UI can show without translating."""

    ok: bool
    reason: str
    chars: int = 0

    @property
    def kind(self) -> str:
        return "fetched" if self.ok else "unavailable"


def readable_url(url: str) -> str:
    """The page that carries the description, given a posting link.

    Only one rule so far, and it is exact rather than clever: a trailing
    `/apply` is the form. Guessing more than this would risk fetching an
    unrelated page and calling it the posting.
    """
    return _APPLY_SUFFIX.sub("", url) or url


def _robots_for(url: str, client: httpx.Client) -> urllib.robotparser.RobotFileParser | None:
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    if host in _robots:
        return _robots[host]

    parser = urllib.robotparser.RobotFileParser()
    try:
        response = client.get(urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", "")))
        if response.status_code >= 400:
            # No robots.txt is permission, by the standard's own default.
            parser.parse([])
        else:
            parser.parse(response.text.splitlines())
    except httpx.HTTPError:
        # Unreachable robots is not implied consent. Treat it as a refusal by
        # storing None, which the caller reports rather than routes around.
        _robots[host] = None
        return None

    _robots[host] = parser
    return parser


def allowed_by_robots(url: str, client: httpx.Client, user_agent: str) -> bool:
    parser = _robots_for(url, client)
    if parser is None:
        return False
    return parser.can_fetch(user_agent, url)


def fetch_description(
    url: str, *, client: httpx.Client | None = None
) -> tuple[str | None, FetchResult]:
    """Fetch and flatten one posting page. Returns ``(description, result)``."""
    if not url:
        return None, FetchResult(False, "This posting has no link to fetch.")

    owned = client is None
    client = client or build_client()
    try:
        from ..core.config import get_settings

        agent = get_settings().user_agent
        if not allowed_by_robots(url, client, agent):
            return None, FetchResult(
                False,
                "The employer's robots.txt does not allow fetching this page, "
                "so Lighthouse did not.",
            )

        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            return None, FetchResult(False, f"Could not reach the page ({type(exc).__name__}).")

        if response.status_code >= 400:
            return None, FetchResult(
                False,
                f"The employer's page returned {response.status_code}. "
                "The posting may already be closed.",
            )

        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            return None, FetchResult(False, f"That link is not a web page ({content_type or '?'}).")

        body = response.content[:MAX_BYTES].decode(response.encoding or "utf-8", errors="replace")
        text = clean_html(_FURNITURE.sub(" ", body))

        if not text or len(text) < MIN_USEFUL_CHARS:
            return None, FetchResult(
                False,
                "The page carried nothing readable — usually a login wall or a "
                "description rendered by JavaScript after load.",
                chars=len(text or ""),
            )
        if len(text) > MAX_USEFUL_CHARS:
            # Refused rather than truncated. Half a page cut at an arbitrary
            # point is not a description either, and it would look like one.
            return None, FetchResult(
                False,
                "That page is far too long to be a job description — it is likely "
                "an application form. Nothing was saved.",
                chars=len(text),
            )
        return text, FetchResult(True, "Description fetched from the employer's page.", len(text))
    finally:
        if owned:
            client.close()


def refresh_posting(
    session: Session, posting: Posting, *, client: httpx.Client | None = None
) -> FetchResult:
    """Fetch a posting's description and persist it if one was found.

    On success the match index is dropped, because the score the operator is
    looking at was computed from the title alone and is about to change.
    """
    description, result = fetch_description(
        readable_url(posting.url or posting.canonical_url or ""), client=client
    )
    if not result.ok or not description:
        return result

    posting.description = description
    posting.description_available = True
    session.flush()
    ranking.invalidate_cache()
    logger.info("fetched description for %s (%d chars)", posting.id, result.chars)
    return result
