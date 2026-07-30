"""Will an ATS parse this resume, or mangle it before a human sees it?

This is the check that addresses the real fear: not that a resume is weak, but
that a machine garbles it so the recruiter never sees the real thing. Every
finding here is grounded in how parsers actually fail, verified against how
Workday, Greenhouse and Taleo behave:

* **Multi-column layouts** are the most dangerous. Workday reads straight
  across the page, so a two-column resume with skills in a sidebar gets
  interleaved into nonsense. The parser's output *is* what the recruiter and
  the screening AI see -- if your skills were trapped in a sidebar, the ATS has
  no skills to match on.
* **Contact details in the page header or footer** are dropped by roughly a
  quarter of systems. A resume the ATS cannot attach a name and email to is an
  automatic rejection.
* **Text boxes and tables** are invisible or scrambled.
* **Ligatures and decorative fonts** turn "efficiency" into "ef ciency".
* **Exotic bullets and symbols** get stripped, and some parsers stop reading at
  the character, truncating the rest of the line.

The centrepiece is the **parse preview**: the resume re-extracted the way a
naive ATS reads it, in that order, so the operator can *see* the scramble
rather than be told about it. Nothing here is a score -- it is a ranked list of
concrete problems, each with the specific fix.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import IntEnum

# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


class Severity(IntEnum):
    """Ordered so findings sort worst-first. Critical issues are the ones that
    actually cause an auto-reject or a garbled parse; warnings degrade the
    result; minor items are polish."""

    CRITICAL = 3
    WARNING = 2
    MINOR = 1


@dataclass(slots=True)
class Finding:
    severity: Severity
    category: str
    title: str
    detail: str
    fix: str
    evidence: str | None = None


@dataclass(slots=True)
class ParsePreview:
    """What the operator laid out vs what a naive ATS extracts.

    When ``scrambled`` is true, ``ats_text`` is materially out of order relative
    to ``visual_text`` -- the concrete demonstration that the layout is unsafe.
    """

    visual_text: str
    ats_text: str
    scrambled: bool
    column_count: int


@dataclass(slots=True)
class AtsReport:
    findings: list[Finding] = field(default_factory=list)
    preview: ParsePreview | None = None
    page_count: int = 0
    char_count: int = 0
    word_count: int = 0
    fonts: list[str] = field(default_factory=list)

    @property
    def critical(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.CRITICAL]

    @property
    def will_parse_cleanly(self) -> bool:
        """No critical issues. The honest headline: not a score, a yes/no on
        whether the resume survives the machine intact."""
        return not self.critical

    def verdict(self) -> str:
        crit = len(self.critical)
        if crit:
            return (
                f"{crit} issue{'s' if crit != 1 else ''} likely to cause an auto-reject "
                "or a garbled parse"
            )
        warnings = sum(1 for f in self.findings if f.severity is Severity.WARNING)
        if warnings:
            return f"Should parse, but {warnings} thing{'s' if warnings != 1 else ''} to tighten"
        return "Clean parse — the ATS should see your resume the way you wrote it"

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (-f.severity, f.category))


# --------------------------------------------------------------------------
# Character and font risk tables (grounded in the research above)
# --------------------------------------------------------------------------

# Precomposed ligatures. When a decorative font is substituted on the ATS
# server these extract as missing characters ("ef ciency").
_LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
    "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st",
}  # fmt: skip

# Bullet and symbol glyphs that parsers strip or choke on. Standard bullets
# ("•", "-", "*") are intentionally absent -- those are safe.
_RISKY_BULLETS = set("▪▸►▶◆◇○●■□➤➢➔✦✓✔★☆❖‣⁃∎♦❯»‒")
_RISKY_SYMBOLS = set("→⇒⟶↦⟹★☆✦✧♦❖✱✲✳➔➜⟩")
# Smart punctuation is usually fine in modern parsers but worth a minor note
# only when it is heavy; handled separately from hard-risk glyphs.

# Fonts commonly used in design tools that are NOT installed on ATS servers, so
# the server substitutes another face and can break ligatures/metrics.
_NON_ATS_FONTS = {
    "avenir", "montserrat", "proximanova", "proxima nova", "poppins", "gotham",
    "circular", "futura", "brandon", "gilroy", "raleway", "lato light",
    "century gothic", "helvetica neue light", "museo", "sofia",
}  # fmt: skip

# Faces that parse reliably everywhere.
_SAFE_FONTS = {
    "arial", "helvetica", "calibri", "times new roman", "times", "georgia",
    "garamond", "verdana", "tahoma", "cambria", "book antiqua", "trebuchet",
    "liberation", "carlito", "dejavu sans", "roboto", "open sans", "lato",
    "source sans", "pt sans",
}  # fmt: skip

# Section headings an ATS maps to structured fields. If a resume's headings do
# not resemble these, the content may not populate the fields recruiters filter.
_STANDARD_SECTIONS = {
    "experience", "work experience", "employment", "professional experience",
    "education", "skills", "technical skills", "projects", "certifications",
    "summary", "objective", "awards", "publications", "activities", "leadership",
}  # fmt: skip

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
# A heading line: short, no trailing sentence punctuation.
_HEADING_RE = re.compile(r"^[A-Z][A-Za-z /&]{2,40}$")
# Employment date ranges the ATS uses to compute tenure.
_DATE_RANGE_RE = re.compile(
    r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s*)?\d{4}\s*"
    r"(?:-|–|—|to|present|current)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Geometry: the multi-column detector and the parse preview
# --------------------------------------------------------------------------


def _cluster_lines(words: list[dict], tolerance: float = 3.0) -> list[list[dict]]:
    """Group words into visual lines by their vertical position."""
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (round(w["top"] / tolerance), w["x0"]))
    lines: list[list[dict]] = []
    current: list[dict] = []
    current_top: float | None = None
    for word in ordered:
        if current_top is None or abs(word["top"] - current_top) <= tolerance:
            current.append(word)
            current_top = word["top"] if current_top is None else current_top
        else:
            lines.append(current)
            current = [word]
            current_top = word["top"]
    if current:
        lines.append(current)
    return lines


def _find_gutter(words: list[dict], page_width: float, page_height: float) -> float | None:
    """Locate a vertical gutter that splits the page into columns.

    Scans candidate x positions across the middle of the page and returns the
    one that the fewest words cross while dividing content roughly in half. A
    real two-column layout has a clean vertical band no word spans; a
    single-column resume has words crossing every interior x.
    """
    if not words or page_width <= 0:
        return None

    # Only the body matters; ignore the top slice where a full-width name/header
    # legitimately spans the page.
    body = [w for w in words if w["top"] > page_height * 0.12]
    if len(body) < 20:
        return None

    best_x: float | None = None
    best_crossings = len(body)
    # Candidate gutters live in the central band of the page.
    start, end = int(page_width * 0.3), int(page_width * 0.7)
    for x in range(start, end, 4):
        crossings = sum(1 for w in body if w["x0"] < x < w["x1"])
        if crossings > best_crossings:
            continue
        left = sum(1 for w in body if w["x1"] <= x)
        right = sum(1 for w in body if w["x0"] >= x)
        # Both sides must hold real content for this to be a column boundary.
        if left < len(body) * 0.15 or right < len(body) * 0.15:
            continue
        if crossings < best_crossings:
            best_crossings = crossings
            best_x = float(x)

    # A gutter is only real if almost nothing crosses it.
    if best_x is not None and best_crossings <= max(2, len(body) * 0.02):
        return best_x
    return None


def _text_in_reading_order(words: list[dict], tolerance: float = 3.0) -> str:
    """Naive left-to-right, top-to-bottom extraction -- what a simple parser
    does. Over a multi-column layout this is exactly the scramble."""
    lines = _cluster_lines(words, tolerance)
    return "\n".join(
        " ".join(w["text"] for w in sorted(line, key=lambda w: w["x0"])) for line in lines
    )


def _text_column_aware(words: list[dict], gutter: float, tolerance: float = 3.0) -> str:
    """Read the left column fully, then the right -- the layout the human sees.
    Used only to contrast against the naive read."""
    left = [w for w in words if w["x1"] <= gutter]
    right = [w for w in words if w["x0"] >= gutter]
    spanning = [w for w in words if w["x0"] < gutter < w["x1"]]  # full-width header
    parts = []
    if spanning:
        parts.append(_text_in_reading_order(spanning, tolerance))
    parts.append(_text_in_reading_order(left, tolerance))
    parts.append(_text_in_reading_order(right, tolerance))
    return "\n".join(p for p in parts if p.strip())


def _normalized_lines(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def build_parse_preview(words: list[dict], page_width: float, page_height: float) -> ParsePreview:
    """Contrast the visual reading order with the naive ATS reading order."""
    ats_text = _text_in_reading_order(words)
    gutter = _find_gutter(words, page_width, page_height)

    if gutter is None:
        return ParsePreview(
            visual_text=ats_text, ats_text=ats_text, scrambled=False, column_count=1
        )

    visual_text = _text_column_aware(words, gutter)
    # Scrambled when the naive read reorders content -- i.e. the two extractions
    # disagree on line order. Compared on normalised lines so whitespace noise
    # does not register as a difference.
    scrambled = _normalized_lines(ats_text) != _normalized_lines(visual_text)
    return ParsePreview(
        visual_text=visual_text, ats_text=ats_text, scrambled=scrambled, column_count=2
    )


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------


def _check_extractable(char_count: int, page_count: int) -> Finding | None:
    if page_count and char_count < 100:
        return Finding(
            Severity.CRITICAL,
            "extraction",
            "The ATS extracts almost no text",
            f"Only {char_count} characters came out of {page_count} page(s). The resume is "
            "almost certainly an image (a scanned page, or a design-tool export). An ATS "
            "reads zero text from it, which is an automatic rejection.",
            "Export as a real text PDF from Google Docs or Word (File → Download → PDF). "
            "Do not print-to-image or export a flattened design.",
        )
    return None


def _check_columns(preview: ParsePreview | None) -> Finding | None:
    if preview and preview.column_count > 1 and preview.scrambled:
        left = _normalized_lines(preview.ats_text)[:3]
        return Finding(
            Severity.CRITICAL,
            "layout",
            "A multi-column layout scrambles when parsed",
            "Your resume uses columns. Workday and many other systems read straight across "
            "the page, interleaving the columns. See the parse preview: this is the order the "
            "recruiter's system receives, and anything trapped in a sidebar (often skills) is "
            "effectively lost.",
            "Switch to a single-column layout. It is the single most important change for "
            "getting past the parser.",
            evidence=" ⏎ ".join(left) if left else None,
        )
    return None


def _check_contact(words: list[dict], full_text: str, page_height: float) -> list[Finding]:
    findings: list[Finding] = []
    has_email = bool(_EMAIL_RE.search(full_text))
    has_phone = bool(_PHONE_RE.search(full_text))

    # Which region does the contact info live in? Header/footer text is dropped
    # by ~a quarter of systems.
    header_cut = page_height * 0.08
    footer_cut = page_height * 0.92
    body_words = " ".join(w["text"] for w in words if header_cut < w["top"] < footer_cut)
    margin_words = " ".join(
        w["text"] for w in words if w["top"] <= header_cut or w["top"] >= footer_cut
    )

    email_in_body = bool(_EMAIL_RE.search(body_words))
    phone_in_body = bool(_PHONE_RE.search(body_words))
    email_in_margin = bool(_EMAIL_RE.search(margin_words))

    if not has_email:
        findings.append(
            Finding(
                Severity.CRITICAL,
                "contact",
                "No email address found",
                "No email could be extracted from the resume text. If the ATS cannot find an "
                "email, it cannot build a candidate record — an automatic rejection.",
                "Put your email on the first line of the body, as plain selectable text.",
            )
        )
    elif email_in_margin and not email_in_body:
        findings.append(
            Finding(
                Severity.CRITICAL,
                "contact",
                "Your email is in the page header/footer",
                "The email was found only in the header or footer region. Roughly a quarter of "
                "ATS ignore those regions entirely, leaving the recruiter no way to reach you.",
                "Move all contact details into the first line of the document body, not the "
                "header or footer.",
            )
        )
    if not has_phone:
        findings.append(
            Finding(
                Severity.WARNING,
                "contact",
                "No phone number found",
                "No phone number could be extracted. Some applications treat it as required.",
                "Add a phone number in plain text next to your email.",
            )
        )
    elif not phone_in_body and has_phone:
        findings.append(
            Finding(
                Severity.WARNING,
                "contact",
                "Your phone number is in the header/footer",
                "The phone number sits in a region some parsers drop.",
                "Move it into the body with the rest of your contact line.",
            )
        )
    return findings


def _check_glyphs(full_text: str) -> list[Finding]:
    findings: list[Finding] = []

    ligatures = {ch for ch in full_text if ch in _LIGATURES}
    if ligatures:
        sample = ", ".join(f"{ch!r}→{_LIGATURES[ch]}" for ch in sorted(ligatures))
        findings.append(
            Finding(
                Severity.WARNING,
                "characters",
                "Ligature characters may extract with missing letters",
                "The text contains typographic ligatures. When an ATS substitutes a font, these "
                "can extract as gaps — 'efficiency' becomes 'ef ciency' — corrupting keywords.",
                "Retype the affected words, or export with a standard font (Arial, Calibri) that "
                "does not rely on ligatures.",
                evidence=sample,
            )
        )

    bullets = {ch for ch in full_text if ch in _RISKY_BULLETS}
    if bullets:
        findings.append(
            Finding(
                Severity.WARNING,
                "characters",
                "Non-standard bullet characters",
                f"Bullets like {' '.join(sorted(bullets))} are stripped by some parsers, and a "
                "few stop reading at the character — truncating the rest of the line.",
                "Use a standard round bullet (•) or a hyphen (-).",
                evidence=" ".join(sorted(bullets)),
            )
        )

    symbols = {ch for ch in full_text if ch in _RISKY_SYMBOLS}
    if symbols:
        findings.append(
            Finding(
                Severity.MINOR,
                "characters",
                "Decorative symbols in the text",
                f"Symbols like {' '.join(sorted(symbols))} can be dropped during extraction.",
                "Replace with plain words where the meaning matters.",
            )
        )
    return findings


def _check_fonts(fonts: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    lowered = [f.lower() for f in fonts]

    non_ats = {f for f in lowered if any(bad in f for bad in _NON_ATS_FONTS)}
    if non_ats:
        findings.append(
            Finding(
                Severity.WARNING,
                "fonts",
                "A design font not installed on ATS servers",
                "Fonts like these are not present on most ATS servers, so the system substitutes "
                "another face. Substitution is where ligature and spacing corruption creeps in.",
                "Set the resume in a universally available face: Arial, Calibri, Helvetica, "
                "Georgia or Times New Roman.",
                evidence=", ".join(sorted(non_ats)),
            )
        )

    recognised = non_ats | {f for f in lowered if any(ok in f for ok in _SAFE_FONTS)}
    if fonts and not recognised:
        findings.append(
            Finding(
                Severity.MINOR,
                "fonts",
                "Uncommon font — verify it parses",
                "The resume uses a font not on the common safe list. It may be fine, but it is "
                "worth confirming the text extracts cleanly.",
                "When in doubt, switch to Arial or Calibri.",
                evidence=", ".join(fonts[:4]),
            )
        )
    return findings


def _check_sections(full_text: str) -> Finding | None:
    headings = [
        line.strip()
        for line in full_text.splitlines()
        if _HEADING_RE.match(line.strip()) and len(line.strip().split()) <= 4
    ]
    matched = [h for h in headings if h.lower() in _STANDARD_SECTIONS]
    # Only flag when the resume clearly has headings but none are standard --
    # otherwise a heading-light resume produces a false alarm.
    if len(headings) >= 3 and not matched:
        return Finding(
            Severity.WARNING,
            "sections",
            "Section headings the ATS may not recognise",
            "None of the detected headings match the standard names (Experience, Education, "
            "Skills…). An ATS maps content to fields by these headings; unusual ones like 'What "
            "I've Built' can leave your experience out of the structured record recruiters "
            "filter on.",
            "Use conventional headings: Experience, Education, Skills, Projects.",
            evidence=", ".join(headings[:5]),
        )
    return None


def _check_dates(full_text: str) -> Finding | None:
    # Only relevant when there is an Experience section to date.
    if "experience" not in full_text.lower() and "employment" not in full_text.lower():
        return None
    if not _DATE_RANGE_RE.search(full_text):
        return Finding(
            Severity.MINOR,
            "dates",
            "Employment dates may not be machine-readable",
            "No standard date ranges (e.g. 'Jun 2025 – Present') were found. Some ATS compute "
            "tenure and years-of-experience from these, and unparseable dates can misfile you.",
            "Write dates as 'Mon YYYY – Mon YYYY' or 'Mon YYYY – Present'.",
        )
    return None


def _check_length(page_count: int, employment_type_hint: str | None) -> Finding | None:
    # For students and new grads, more than one page is a mild flag; for
    # experienced roles it is fine, so this stays MINOR and hint-aware.
    if page_count > 1 and (employment_type_hint in (None, "internship", "new_grad")):
        return Finding(
            Severity.MINOR,
            "length",
            f"{page_count} pages",
            "For an internship or new-grad application a single page is the norm; a second page "
            "often means content the reader never reaches.",
            "Trim to one page unless you have publications or substantial experience.",
        )
    return None


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def _collect_words_and_fonts(
    path: str,
) -> tuple[list[list[dict]], list[str], list[tuple[float, float]]]:
    """Pull per-page words (with geometry) and font names.

    Returns (pages_of_words, font_names, page_dimensions). Kept in one place so
    the PDF is opened once.
    """
    import pdfplumber

    pages_words: list[list[dict]] = []
    dims: list[tuple[float, float]] = []
    fonts: set[str] = set()

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            pages_words.append(words)
            dims.append((page.width, page.height))
            for ch in page.chars:
                name = ch.get("fontname", "")
                # Strip the subset prefix ATS-irrelevant "ABCDEF+".
                fonts.add(re.sub(r"^[A-Z]{6}\+", "", name))

    return pages_words, sorted(f for f in fonts if f), dims


def check_resume(path: str, *, employment_type_hint: str | None = None) -> AtsReport:
    """Run the full battery against a resume PDF.

    Analyses the first page's geometry for the layout and contact checks (the
    parse-critical ones almost always live there) and the full text for
    character, font, section and date checks.
    """
    try:
        pages_words, fonts, dims = _collect_words_and_fonts(path)
    except Exception as exc:  # noqa: BLE001 - a PDF we cannot open is itself a finding
        report = AtsReport()
        report.findings.append(
            Finding(
                Severity.CRITICAL,
                "extraction",
                "The file could not be read as a PDF",
                f"Opening the file failed ({exc}). If it is a .pages, .docx or image, most ATS "
                "will not read it either.",
                "Export a standard text PDF from Google Docs or Word and re-upload.",
            )
        )
        return report

    report = AtsReport(page_count=len(pages_words), fonts=fonts)
    all_words = [w for page in pages_words for w in page]
    report.word_count = len(all_words)

    full_text = "\n".join(_text_in_reading_order(page) for page in pages_words)
    report.char_count = len(full_text.replace("\n", "").strip())

    # Layout + contact from the first page's geometry.
    if pages_words and pages_words[0]:
        page_w, page_h = dims[0]
        report.preview = build_parse_preview(pages_words[0], page_w, page_h)
        report.findings.extend(_check_contact(pages_words[0], full_text, page_h))

    # Ordered battery; each returns a finding or list of them, or None.
    single = [
        _check_extractable(report.char_count, report.page_count),
        _check_columns(report.preview),
        _check_sections(full_text),
        _check_dates(full_text),
        _check_length(report.page_count, employment_type_hint),
    ]
    report.findings.extend(f for f in single if f is not None)
    report.findings.extend(_check_glyphs(full_text))
    report.findings.extend(_check_fonts(fonts))

    # Deduplicate contact findings if both extract paths flagged the same thing.
    seen: set[tuple[str, str]] = set()
    unique: list[Finding] = []
    for finding in report.findings:
        key = (finding.category, finding.title)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    report.findings = unique
    return report


def normalize_text_for_ligatures(text: str) -> str:
    """Expand ligatures to their component letters. Used when comparing extracted
    resume text against a job description, so a ligature-corrupted 'ef ciency'
    does not silently miss the keyword 'efficiency'."""
    for lig, expansion in _LIGATURES.items():
        text = text.replace(lig, expansion)
    return unicodedata.normalize("NFKC", text)
