"""Turning a resume PDF into draft corpus facts.

Two jobs, kept separate:

* **Extraction for review.** Split a resume into candidate facts (projects,
  experiences, skills) that the operator then corrects. These are drafts, never
  committed silently -- the zero-fabrication rule means the operator confirms
  what is real. Deliberately heuristic: a wrong split is cheap to fix, an
  invented detail is not, so the parser errs toward under-structuring.

* **Layout inspection for the ATS check.** The same PDF read the way an ATS
  parser reads it, so a resume that looks fine but extracts as garbled text can
  be caught before it costs an application. That lives in the Track module; the
  raw text and per-page word geometry it needs are produced here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .corpus import FactInput

# Section headers, and the fact_type each maps to. Kept broad because resumes
# name these sections every possible way ("What I've Built", "Selected Work").
_SECTION_MAP: tuple[tuple[str, str], ...] = (
    (r"experience|employment|work history|professional", "experience"),
    (r"projects?|selected work|things i.?ve built|portfolio", "project"),
    (r"skills?|technolog|technical|proficienc|tools?", "skill"),
    (r"education|academic", "education"),
    (r"awards?|honors?|achievements?|accomplishments?|publications?", "achievement"),
)

_HEADER_RE = re.compile(
    r"^\s*(" + "|".join(pat for pat, _ in _SECTION_MAP) + r")\b\s*:?\s*$",
    re.IGNORECASE,
)

# A bullet line: the leading glyph is stripped, the text kept.
_BULLET_RE = re.compile(r"^\s*[•▪●‣⁃∙*+\-–—]\s+")

# An entry heading inside a section, e.g. "Software Engineer Intern, Acme --
# Jun 2025". Title-ish line, not a bullet, often with a date.
_DATE_HINT_RE = re.compile(
    r"\b(19|20)\d{2}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b",
    re.IGNORECASE,
)

# Skills lines are comma/pipe separated runs of short noun phrases.
_SKILL_SPLIT_RE = re.compile(r"\s*[,;|/•]\s*|\s{3,}")


@dataclass(slots=True)
class ExtractedResume:
    """The result of parsing a resume: draft facts plus the raw material the
    ATS check needs."""

    facts: list[FactInput] = field(default_factory=list)
    raw_text: str = ""
    char_count: int = 0
    page_count: int = 0
    # True when extraction produced almost no text, which usually means the
    # resume is an image rather than selectable text -- an ATS would get
    # nothing from it either.
    likely_image_based: bool = False


def _classify_section(line: str) -> str | None:
    match = _HEADER_RE.match(line.strip())
    if not match:
        return None
    header = match.group(1).lower()
    for pattern, fact_type in _SECTION_MAP:
        if re.search(pattern, header):
            return fact_type
    return None


def _looks_like_heading(line: str) -> bool:
    """Whether a non-bullet line starts a new entry within a section."""
    stripped = line.strip()
    if not stripped or _BULLET_RE.match(line):
        return False
    if len(stripped) > 90:
        return False
    # An enumeration ("Coursework: algorithms, data structures, OS") is body
    # content, not a heading -- several commas is the tell.
    if stripped.count(",") >= 2:
        return False
    return bool(_DATE_HINT_RE.search(stripped)) or stripped[:1].isupper()


def _flush(facts: list[FactInput], fact_type: str, title: str, bullets: list[str]) -> None:
    if not title.strip() and not bullets:
        return
    body = "\n".join(bullets).strip()
    # A titled entry with no bullets (common in Education) must keep its title;
    # only fall back to the first bullet when there is genuinely no title.
    display_title = title.strip() or (bullets[0] if bullets else "Untitled")
    facts.append(FactInput(fact_type=fact_type, title=display_title[:200], body=body))


def facts_from_text(text: str) -> list[FactInput]:
    """Split resume text into draft facts.

    Walks the document section by section. Inside a section, a heading-like
    line starts a new entry and bullets attach to it. Skills sections are split
    into individual skill facts, since that is how they are used downstream.
    """
    facts: list[FactInput] = []
    current_type = "experience"
    current_title = ""
    current_bullets: list[str] = []
    in_section = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        section = _classify_section(line)
        if section is not None:
            _flush(facts, current_type, current_title, current_bullets)
            current_type, current_title, current_bullets = section, "", []
            in_section = True
            continue

        if not in_section:
            # Preamble (name, contact line) before the first header -- skip it.
            continue

        if current_type == "skill":
            for token in _SKILL_SPLIT_RE.split(line.strip()):
                token = token.strip(" .-•")
                if 1 < len(token) <= 40:
                    facts.append(FactInput(fact_type="skill", title=token, body=""))
            continue

        if _BULLET_RE.match(line):
            current_bullets.append(_BULLET_RE.sub("", line).strip())
        elif _looks_like_heading(line):
            _flush(facts, current_type, current_title, current_bullets)
            current_title, current_bullets = line.strip(), []
        else:
            current_bullets.append(line.strip())

    _flush(facts, current_type, current_title, current_bullets)
    return facts


def extract_pdf(path: str) -> ExtractedResume:
    """Parse a resume PDF into draft facts and raw text.

    ``pdfplumber`` is imported lazily so the ingestion pipeline -- which never
    touches PDFs -- does not pay for it. If under 100 characters come out of a
    one-page document, the resume is almost certainly an image, which is
    flagged rather than silently returning nothing.
    """
    import pdfplumber

    pages_text: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")

    raw_text = "\n".join(pages_text).strip()
    result = ExtractedResume(
        facts=facts_from_text(raw_text),
        raw_text=raw_text,
        char_count=len(raw_text),
        page_count=len(pages_text),
    )
    result.likely_image_based = result.char_count < 100 and result.page_count >= 1
    return result
