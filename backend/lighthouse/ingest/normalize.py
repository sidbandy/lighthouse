"""Normalisation shared by every connector.

Feeds disagree about everything: whitespace, suffixes, tracking parameters,
how locations are spelled. Dedup can only work if all of them are reduced to
the same shape first, so this module is deliberately the single place those
rules live.

The subtle one is :func:`canonical_url`. Stripping query parameters is normally
safe, but ``gh_jid`` (Greenhouse), ``jobId`` (Ashby/Workday) and friends are
*identity-bearing*: they are the job, not a tracking tag. Dropping them would
merge every Greenhouse role at a company into one row.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..core.models import EmploymentType, RoleFamily, Sponsorship

# Query parameters that identify *which* job. Never stripped.
IDENTITY_PARAMS: frozenset[str] = frozenset(
    {
        "gh_jid",
        "gh_job_id",
        "jobid",
        "job_id",
        "jid",
        "req_id",
        "reqid",
        "requisitionid",
        "postingid",
        "posting_id",
        "vacancyid",
    }
)

# Tracking parameters, always stripped.
_TRACKING_PREFIXES = ("utm_", "hsa_", "mc_", "pk_")
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "source",
        "src",
        "ref",
        "referrer",
        "gh_src",
        "fbclid",
        "gclid",
        "msclkid",
        "trk",
        "trackingid",
        "lever-source",
        "campaign",
        "medium",
    }
)

# Legal suffixes dropped when blocking companies for dedup. Conservative on
# purpose: better to keep two rows than merge two different companies.
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(inc|inc\.|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|"
    r"plc|gmbh|s\.a|sa|nv|ag|holdings|group|technologies|labs)\b\.?",
    re.IGNORECASE,
)

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")

# Noise that appears in scraped titles but does not distinguish a role.
_TITLE_NOISE_RE = re.compile(
    r"\b(20\d{2}|summer|fall|autumn|winter|spring|intern(ship)?s?|co-?op|"
    r"student|program|programme|new\s*grad(uate)?|entry\s*level|university|campus)\b",
    re.IGNORECASE,
)

_REMOTE_RE = re.compile(r"\b(remote|anywhere|work\s*from\s*home|wfh|virtual)\b", re.IGNORECASE)

_US_STATES: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}  # fmt: skip

# ATS vendor detection from a posting URL. Knowing the vendor unlocks a public
# JSON board API and tells the ATS resume check which parser to model.
_ATS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("greenhouse", re.compile(r"(greenhouse\.io|gh_jid=)", re.IGNORECASE)),
    ("ashby", re.compile(r"ashbyhq\.com", re.IGNORECASE)),
    ("lever", re.compile(r"lever\.co", re.IGNORECASE)),
    ("workday", re.compile(r"myworkday(jobs|site)\.com", re.IGNORECASE)),
    ("smartrecruiters", re.compile(r"smartrecruiters\.com", re.IGNORECASE)),
    ("workable", re.compile(r"workable\.com", re.IGNORECASE)),
    ("recruitee", re.compile(r"recruitee\.com", re.IGNORECASE)),
    ("icims", re.compile(r"icims\.com", re.IGNORECASE)),
    ("taleo", re.compile(r"taleo\.net", re.IGNORECASE)),
    ("jobvite", re.compile(r"jobvite\.com", re.IGNORECASE)),
    ("breezy", re.compile(r"breezy\.hr", re.IGNORECASE)),
    ("rippling", re.compile(r"rippling(ats)?\.com", re.IGNORECASE)),
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def canonical_company(name: str) -> str:
    """Blocking key for a company name.

    ``"Optiver US, LLC "`` and ``"optiver us"`` collapse to the same key, which
    is what lets dedup compare only rows that could plausibly match.
    """
    text = strip_accents(name or "").lower()
    text = text.replace("&", " and ")
    text = _PUNCT_RE.sub(" ", text)
    text = _COMPANY_SUFFIX_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    """Comparison form of a role title.

    Season, year and the word "intern" are stripped because they vary between
    feeds describing the same role. What remains is the discriminating part
    ("software engineer", "quantitative trader").
    """
    text = strip_accents(title or "").lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _TITLE_NOISE_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def extract_ats(url: str) -> str | None:
    """Which ATS vendor hosts this posting, if recognisable."""
    for vendor, pattern in _ATS_PATTERNS:
        if pattern.search(url or ""):
            return vendor
    return None


def extract_job_id(url: str) -> str | None:
    """The ATS job id, which is an absolute identity signal for dedup.

    Looks in the query string first (``?gh_jid=8003019``), then falls back to a
    long numeric path segment, which is how Ashby, Lever and Workday encode it.
    """
    if not url:
        return None
    parts = urlsplit(url)
    for key, value in parse_qsl(parts.query):
        if key.lower() in IDENTITY_PARAMS and value.strip():
            return value.strip()
    for segment in reversed(parts.path.strip("/").split("/")):
        if segment.isdigit() and len(segment) >= 6:
            return segment
        # Ashby/Lever use UUIDs in the final path segment.
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", segment):
            return segment
    return None


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    if lowered in IDENTITY_PARAMS:
        return False
    return lowered.startswith(_TRACKING_PREFIXES) or lowered in _TRACKING_PARAMS


def canonical_url(url: str) -> str:
    """Strip tracking noise while preserving job identity.

    Two rows resolving to the same canonical URL are the same posting -- this
    catches the majority of cross-feed duplicates cheaply, before any fuzzy
    matching is needed.
    """
    if not url:
        return ""
    parts = urlsplit(url.strip())
    if not parts.scheme:
        parts = urlsplit(f"https://{url.strip()}")

    kept = sorted((k, v) for k, v in parse_qsl(parts.query) if not _is_tracking(k))
    netloc = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    # Fragments are never identity-bearing for job boards.
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(kept), ""))


def parse_location(raw: str) -> dict:
    """Parse a location string into ``{city, state, raw, is_remote}``.

    Feeds write locations every possible way; this keeps the original text so
    nothing is lost, and adds structure where it can be recovered.
    """
    text = _WS_RE.sub(" ", (raw or "").strip())
    if not text:
        return {"city": None, "state": None, "raw": "", "is_remote": False}

    is_remote = bool(_REMOTE_RE.search(text))
    city: str | None = None
    state: str | None = None

    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 2:
        city = parts[0]
        tail = parts[1].strip()
        if re.fullmatch(r"[A-Za-z]{2}", tail):
            state = tail.upper()
        else:
            state = _US_STATES.get(tail.lower())
            if state is None and tail.lower() in {v.lower() for v in _US_STATES.values()}:
                state = tail.upper()
    elif len(parts) == 1 and not is_remote:
        single = parts[0]
        state = _US_STATES.get(single.lower())
        if state is None:
            city = single

    return {"city": city, "state": state, "raw": text, "is_remote": is_remote}


def location_label(parsed: dict) -> str:
    """Short display/filter label: ``"Austin, TX"``, ``"Remote"``."""
    if parsed.get("city") and parsed.get("state"):
        return f"{parsed['city']}, {parsed['state']}"
    if parsed.get("is_remote"):
        return "Remote"
    return parsed.get("raw") or ""


def classify_role_family(title: str) -> RoleFamily:
    """Bucket a title into a role family from keywords.

    Order matters: "ML infrastructure engineer" should land in AI/ML, so the
    more specific families are tested before the general SWE catch-all.
    """
    text = f" {normalize_title(title)} "
    if re.search(r"\b(quant\w*|trading|trader)\b", text):
        return RoleFamily.QUANT
    if re.search(r"\b(machine learning|ml|ai|deep learning|nlp|computer vision|research)\b", text):
        return RoleFamily.AI_ML
    if re.search(r"\b(security|infosec|appsec|cryptograph\w+)\b", text):
        return RoleFamily.SECURITY
    if re.search(
        r"\b(data (scien\w+|engineer\w*|analy\w+)|analytics|business intelligence)\b", text
    ):
        return RoleFamily.DATA
    if re.search(r"\b(hardware|asic|fpga|electrical|mechanical|silicon|embedded|firmware)\b", text):
        return RoleFamily.HARDWARE
    if re.search(r"\b(product manage\w*|product owner|pm)\b", text):
        return RoleFamily.PRODUCT
    if re.search(
        r"\b(software|engineer\w*|developer|sde|swe|programm\w+|full stack|backend|frontend)\b",
        text,
    ):
        return RoleFamily.SWE
    return RoleFamily.OTHER


def classify_employment_type(title: str, hint: str | None = None) -> EmploymentType:
    """Internship vs new-grad, from the title (or an explicit feed hint)."""
    if hint:
        lowered = hint.lower()
        if "intern" in lowered or "co-op" in lowered or "coop" in lowered:
            return EmploymentType.INTERNSHIP
        if "grad" in lowered or "entry" in lowered:
            return EmploymentType.NEW_GRAD

    text = f" {strip_accents(title or '').lower()} "
    if re.search(r"\b(intern(ship)?s?|co-?op|summer analyst|placement)\b", text):
        return EmploymentType.INTERNSHIP
    if re.search(r"\b(new\s*grad(uate)?|entry[\s-]*level|university grad|campus hire)\b", text):
        return EmploymentType.NEW_GRAD
    return EmploymentType.OTHER


def parse_sponsorship(raw: str | None) -> Sponsorship:
    """Map a feed's sponsorship wording onto our enum.

    Sponsorship is a top-level filter: showing roles the operator is not
    eligible for is a waste of their attention.
    """
    if not raw:
        return Sponsorship.UNKNOWN
    text = raw.lower()
    if "citizen" in text or "🇺🇸" in raw:
        return Sponsorship.CITIZENSHIP_REQUIRED
    if "does not offer" in text or "no sponsor" in text or "🛂" in raw:
        return Sponsorship.DOES_NOT_OFFER
    if "offers sponsor" in text or "will sponsor" in text:
        return Sponsorship.OFFERS
    return Sponsorship.UNKNOWN
