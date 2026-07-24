"""A markdown table parser that tolerates human-edited files.

The curated internship repos are edited by hundreds of contributors, so their
tables contain everything: embedded HTML, ``<details>`` blocks wrapping several
locations, ``<br>`` inside cells, emoji flags carrying real meaning, rows with
the wrong number of columns, and escaped pipes.

Two rules drive the design:

* **Never raise on a bad row.** One malformed row must not cost us the other
  four thousand. Bad rows are skipped and counted.
* **``↳`` means "same company as the row above".** Roughly a third of rows in
  these files use it, so failing to carry the company forward would silently
  lose attribution on a large fraction of the list.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

# A cell's pipe may be escaped (``\|``) or inside an HTML attribute; split on
# unescaped pipes only.
_SPLIT_RE = re.compile(r"(?<!\\)\|")
_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
_TAG_RE = re.compile(r"<[^>]+>")
_BREAK_RE = re.compile(r"<\s*/?\s*br\s*/?\s*>", re.IGNORECASE)
_DETAILS_SUMMARY_RE = re.compile(r"<summary>.*?</summary>", re.IGNORECASE | re.DOTALL)
_MD_LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<href>[^)]+)\)")
_HREF_RE = re.compile(r"""href\s*=\s*["'](?P<href>[^"']+)["']""", re.IGNORECASE)
_BOLD_RE = re.compile(r"\*{1,3}|_{2,3}")

# Emoji flags are semantic in these files, not decoration.
CLOSED_MARKERS = ("🔒", "⛔")
NO_SPONSORSHIP_MARKERS = ("🛂",)
CITIZENSHIP_MARKERS = ("🇺🇸",)

# "same as above" continuation marker used in the Company column.
CONTINUATION_MARKERS = ("↳", "â³", "&#8627;", "↳")


@dataclass
class ParsedRow:
    """One table row, already cleaned and column-mapped."""

    cells: dict[str, str]
    links: dict[str, list[str]]
    raw_line: str

    def get(self, column: str, default: str = "") -> str:
        return self.cells.get(column, default)

    def first_link(self, column: str) -> str | None:
        values = self.links.get(column) or []
        return values[0] if values else None


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    skipped: int = 0
    tables_found: int = 0

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.rows)


def _split_cells(line: str) -> list[str]:
    stripped = line.strip()
    stripped = stripped.removeprefix("|")
    stripped = stripped.removesuffix("|") if stripped.endswith("|") else stripped
    return [c.replace(r"\|", "|") for c in _SPLIT_RE.split(stripped)]


def extract_links(cell: str) -> list[str]:
    """Every URL in a cell, from both markdown and HTML anchors.

    These tables link out via an image button (``<a href=...><img ...></a>``),
    so the href is the only place the apply URL exists.
    """
    links = [m.group("href").strip() for m in _HREF_RE.finditer(cell)]
    links += [
        m.group("href").strip()
        for m in _MD_LINK_RE.finditer(cell)
        if m.group("href").strip().startswith(("http://", "https://"))
    ]
    seen: set[str] = set()
    return [x for x in links if not (x in seen or seen.add(x))]


def clean_cell(cell: str, *, keep_markers: bool = True) -> str:
    """Reduce a cell to plain text without losing meaning.

    ``<details>`` summaries ("**4 locations**") are dropped because the useful
    content is the list inside them; ``<br>`` becomes a separator so multiple
    locations survive as distinct values.
    """
    text = _DETAILS_SUMMARY_RE.sub(" ", cell)
    text = _BREAK_RE.sub(" ; ", text)
    text = _MD_LINK_RE.sub(lambda m: m.group("text"), text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _BOLD_RE.sub("", text)
    if not keep_markers:
        for marker in (*CLOSED_MARKERS, *NO_SPONSORSHIP_MARKERS, *CITIZENSHIP_MARKERS):
            text = text.replace(marker, " ")
    return re.sub(r"\s+", " ", text).strip(" ;\t\n")


def split_multi(value: str) -> list[str]:
    """Split a cell that holds several values (typically locations)."""
    parts = [p.strip() for p in re.split(r"\s*;\s*|\s*/\s*(?=[A-Z])", value) if p.strip()]
    return parts or ([value.strip()] if value.strip() else [])


def is_continuation(company_cell: str) -> bool:
    """Whether this row inherits the previous row's company."""
    text = clean_cell(company_cell).strip()
    return not text or any(marker in company_cell for marker in CONTINUATION_MARKERS)


def normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", clean_cell(header).lower()).strip("_")


def parse_tables(markdown: str, *, min_columns: int = 3) -> ParseResult:
    """Parse every pipe table in a markdown document.

    Handles multiple tables in one file (the repos separate active from closed
    roles, or split by category) and returns their rows concatenated, keyed by
    normalised header name.
    """
    result = ParseResult()
    headers: list[str] = []
    in_table = False

    for line in markdown.splitlines():
        stripped = line.strip()
        if "|" not in stripped:
            # A blank line or prose ends the current table.
            if in_table and not stripped:
                in_table = False
                headers = []
            continue

        cells = _split_cells(stripped)
        if len(cells) < min_columns:
            continue

        if not in_table:
            candidate = [normalize_header(c) for c in cells]
            if any(candidate):
                headers = candidate
                in_table = True
                result.tables_found += 1
                if not result.headers:
                    result.headers = headers
            continue

        if _SEPARATOR_RE.match(stripped):
            continue

        # Tolerate ragged rows: pad short ones, ignore trailing extras. A row
        # that is wildly wrong is skipped rather than mis-mapped.
        if len(cells) < len(headers) - 1:
            result.skipped += 1
            continue
        padded = cells + [""] * (len(headers) - len(cells))

        mapped: dict[str, str] = {}
        links: dict[str, list[str]] = {}
        for header, cell in zip(headers, padded, strict=False):
            if not header:
                continue
            mapped[header] = cell
            found = extract_links(cell)
            if found:
                links[header] = found

        if mapped:
            result.rows.append(ParsedRow(cells=mapped, links=links, raw_line=stripped))

    return result
