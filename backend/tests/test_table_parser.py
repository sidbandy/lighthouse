"""The markdown table parser is the only thing standing between hand-edited
community files and the ingest pipeline.

Every case here is drawn from something the curated repos actually do: HTML
apply buttons, ``<details>`` location lists, ``↳`` continuations, emoji flags
that carry meaning, and rows with the wrong number of columns. The parser is
expected to survive all of it without raising.
"""

import textwrap

import pytest

from lighthouse.ingest.table_parser import (
    clean_cell,
    extract_links,
    is_continuation,
    normalize_header,
    parse_tables,
    split_multi,
)

APPLY_BUTTON = (
    '<a href="https://boards.greenhouse.io/janestreet/jobs/8003019?gh_jid=8003019">'
    '<img src="https://i.imgur.com/apply.png" alt="Apply"></a>'
)

DETAILS_CELL = (
    "<details><summary>**4 locations**</summary>"
    "New York, NY</br>Greenwich, CT</br>Miami, FL</details>"
)

WELL_FORMED = textwrap.dedent(
    f"""\
    # Internships

    | Company | Role | Location | Application/Link | Date Posted |
    | --- | --- | --- | --- | --- |
    | Jane Street | Software Engineer Intern | New York, NY | {APPLY_BUTTON} | Jul 09 |
    | ↳ | Quantitative Trader Intern | Chicago, IL | [Apply](https://x.com/j) | Jul 08 |
    | Citadel | 🛂 Software Engineer Intern | {DETAILS_CELL} | [Apply](https://c.com/j) | Dec 15 |
    """
)

RAGGED = textwrap.dedent(
    """\
    | Company | Role | Location | Application/Link | Date Posted |
    | --- | --- | --- | --- | --- |
    | Padded Corp | Analyst Intern | Boston, MA | [Apply](https://p.com/1) |
    | Short Corp | Analyst Intern | Boston, MA |
    | Full Corp | Analyst Intern | Boston, MA | [Apply](https://f.com/1) | Jul 01 |
    """
)

ESCAPED_PIPES = textwrap.dedent(
    """\
    | Company | Role | Location | Application/Link | Date Posted |
    | --- | --- | --- | --- | --- |
    | Two Sigma | Software Engineer \\| Data | NYC | [Apply](https://t.com/1) | Jul 01 |
    """
)

TWO_TABLES = textwrap.dedent(
    """\
    ## Open

    | Company | Role | Location | Application/Link | Date Posted |
    | --- | --- | --- | --- | --- |
    | Optiver | Quant Trader Intern | Austin, TX | [Apply](https://o.com/1) | Jul 02 |

    ## Closed

    | Company | Role | Location | Application/Link | Date Posted |
    | --- | --- | --- | --- | --- |
    | IMC | 🔒 SWE Intern | Chicago, IL | [Apply](https://i.com/2) | Jun 30 |
    """
)

NO_TABLES = textwrap.dedent(
    """\
    # Internships

    This list has not been published yet. Use the pipe | character freely.
    """
)


class TestParseTables:
    def test_parses_every_row_of_a_well_formed_table(self):
        result = parse_tables(WELL_FORMED)
        assert len(result.rows) == 3
        assert result.tables_found == 1
        assert result.skipped == 0

    def test_headers_are_normalized_to_snake_case(self):
        """Downstream code looks columns up by name, so header spelling has to
        collapse to one canonical form across repos."""
        result = parse_tables(WELL_FORMED)
        assert result.headers == [
            "company",
            "role",
            "location",
            "application_link",
            "date_posted",
        ]

    def test_rows_are_keyed_by_normalized_header(self):
        row = parse_tables(WELL_FORMED).rows[0]
        assert clean_cell(row.get("company")) == "Jane Street"
        assert clean_cell(row.get("role")) == "Software Engineer Intern"
        assert row.first_link("application_link") == (
            "https://boards.greenhouse.io/janestreet/jobs/8003019?gh_jid=8003019"
        )

    def test_separator_row_is_never_emitted_as_data(self):
        """A ``| --- |`` row mapped as data would become a phantom posting."""
        result = parse_tables(WELL_FORMED)
        assert all("---" not in row.get("company") for row in result.rows)
        assert all(clean_cell(row.get("role")) for row in result.rows)

    def test_multiple_tables_are_all_parsed(self):
        """The repos split active from closed roles; both halves are real data."""
        result = parse_tables(TWO_TABLES)
        assert result.tables_found == 2
        assert [clean_cell(r.get("company")) for r in result.rows] == ["Optiver", "IMC"]

    def test_document_without_tables_returns_empty_result(self):
        """A repo mid-rewrite must not take the run down with an exception."""
        result = parse_tables(NO_TABLES)
        assert result.rows == []
        assert result.tables_found == 0

    def test_escaped_pipe_does_not_split_a_cell(self):
        r"""``\|`` is how contributors write a literal pipe inside a role title."""
        row = parse_tables(ESCAPED_PIPES).rows[0]
        assert row.get("role").strip() == "Software Engineer | Data"
        assert clean_cell(row.get("date_posted")) == "Jul 01"

    def test_emoji_markers_survive_in_the_raw_cell(self):
        """The flags are semantic, so the parser must not scrub them before the
        connector has had a chance to read them."""
        row = parse_tables(WELL_FORMED).rows[2]
        assert "🛂" in row.get("role")


class TestRaggedRows:
    def test_short_row_within_tolerance_is_padded(self):
        result = parse_tables(RAGGED)
        padded = result.rows[0]
        assert clean_cell(padded.get("company")) == "Padded Corp"
        assert padded.get("date_posted") == ""

    def test_wildly_short_row_is_skipped_and_counted(self):
        """Mapping a three-cell row onto five headers would silently shift every
        value into the wrong column."""
        result = parse_tables(RAGGED)
        assert result.skipped == 1
        assert [clean_cell(r.get("company")) for r in result.rows] == [
            "Padded Corp",
            "Full Corp",
        ]


class TestCleanCell:
    def test_details_summary_is_stripped_but_contents_kept(self):
        """The summary is a count ("4 locations"); the locations themselves are
        the data we need."""
        cleaned = clean_cell(DETAILS_CELL)
        assert "4 locations" not in cleaned
        assert cleaned == "New York, NY ; Greenwich, CT ; Miami, FL"

    def test_details_contents_split_into_separate_locations(self):
        assert split_multi(clean_cell(DETAILS_CELL)) == [
            "New York, NY",
            "Greenwich, CT",
            "Miami, FL",
        ]

    def test_markdown_link_reduces_to_its_text(self):
        assert clean_cell("[Apply Here](https://x.com/j)") == "Apply Here"

    def test_html_tags_and_entities_are_resolved(self):
        assert clean_cell("<b>Ernst &amp; Young</b>") == "Ernst & Young"

    def test_bold_markers_are_removed(self):
        assert clean_cell("**Jane Street**") == "Jane Street"

    def test_markers_are_kept_by_default(self):
        assert clean_cell("🛂 Software Engineer Intern") == "🛂 Software Engineer Intern"

    @pytest.mark.parametrize("marker", ["🛂", "🇺🇸", "🔒"])
    def test_markers_are_removed_on_request(self, marker):
        """Once the flag has been read into a field it is noise in the title."""
        assert clean_cell(f"{marker} Software Engineer Intern", keep_markers=False) == (
            "Software Engineer Intern"
        )


class TestSplitMulti:
    def test_single_value_stays_whole(self):
        assert split_multi("New York, NY") == ["New York, NY"]

    def test_slash_before_a_capital_splits(self):
        assert split_multi("Remote/New York") == ["Remote", "New York"]

    def test_empty_value_yields_nothing(self):
        assert split_multi("   ") == []


class TestExtractLinks:
    def test_pulls_href_out_of_an_image_button(self):
        """The apply URL exists only in the anchor; the visible cell is an image."""
        assert extract_links(APPLY_BUTTON) == [
            "https://boards.greenhouse.io/janestreet/jobs/8003019?gh_jid=8003019"
        ]

    def test_handles_a_plain_markdown_link(self):
        assert extract_links("[Apply](https://x.com/j)") == ["https://x.com/j"]

    def test_html_hrefs_are_returned_before_markdown_links(self):
        cell = '[Apply](https://x.com/j) and <a href="https://y.com/j">mirror</a>'
        assert extract_links(cell) == ["https://y.com/j", "https://x.com/j"]

    def test_duplicate_urls_are_collapsed(self):
        """The same posting is often linked twice in one cell (button + text)."""
        cell = '<a href="https://x.com/j"><img src="a.png"></a> [Apply](https://x.com/j)'
        assert extract_links(cell) == ["https://x.com/j"]

    def test_relative_markdown_links_are_ignored(self):
        assert extract_links("[README](./README.md)") == []

    def test_cell_without_links_yields_nothing(self):
        assert extract_links("New York, NY") == []


class TestIsContinuation:
    @pytest.mark.parametrize("cell", ["↳", " ↳ ", "&#8627;", "", "   "])
    def test_continuation_and_empty_cells_inherit(self, cell):
        """``↳`` is used on roughly a third of rows; treating it as a company
        name would lose attribution wholesale."""
        assert is_continuation(cell) is True

    @pytest.mark.parametrize("cell", ["Jane Street", "**Citadel**", "[Optiver](https://o.com)"])
    def test_real_company_names_do_not_inherit(self, cell):
        assert is_continuation(cell) is False


class TestNormalizeHeader:
    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("Application/Link", "application_link"),
            ("Date Posted", "date_posted"),
            ("**Company**", "company"),
            ("Location(s)", "location_s"),
            (" Role ", "role"),
            ("", ""),
        ],
    )
    def test_normalizes(self, header, expected):
        assert normalize_header(header) == expected
