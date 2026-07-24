"""The curated GitHub list connector.

Two things in these files do real damage if handled naively: dates written
without a year (``Jul 09``), and ``↳`` meaning "same company as the row above".
Both are exercised here against a fixture shaped like the real README.
"""

import textwrap
from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from lighthouse.ingest.base import ConnectorError, build_client
from lighthouse.ingest.connectors.markdown_repo import (
    MarkdownRepoConnector,
    parse_posted_date,
)

TODAY = date(2026, 7, 24)

GREENHOUSE_BUTTON = (
    '<a href="https://boards.greenhouse.io/janestreet/jobs/8003019?gh_jid=8003019">'
    '<img src="https://i.imgur.com/apply.png" alt="Apply"></a>'
)
GREENHOUSE_BUTTON_2 = (
    '<a href="https://boards.greenhouse.io/janestreet/jobs/8003020?gh_jid=8003020">'
    '<img src="https://i.imgur.com/apply.png" alt="Apply"></a>'
)
DETAILS_CELL = (
    "<details><summary>**4 locations**</summary>"
    "New York, NY</br>Greenwich, CT</br>Miami, FL</details>"
)
CITADEL_LINK = "[Apply](https://www.citadel.com/careers/3)"
LEVER_LINK = "[Apply](https://jobs.lever.co/palantir/9f8c)"
ASHBY_LINK = "[Apply](https://jobs.ashbyhq.com/ramp/1234)"
TWOSIGMA_LINK = "[Apply](https://careers.twosigma.com/j/12345)"

README = textwrap.dedent(
    f"""\
    # Summer 2027 Internships

    | Company | Role | Location | Application/Link | Date Posted |
    | --- | --- | --- | --- | --- |
    | **Jane Street** | Software Engineer Intern | New York, NY | {GREENHOUSE_BUTTON} | Jul 09 |
    | ↳ | Quantitative Trader Intern | Chicago, IL | {GREENHOUSE_BUTTON_2} | Jul 08 |
    | Citadel | Software Engineer Intern | {DETAILS_CELL} | {CITADEL_LINK} | Jul 05 |
    | Palantir | 🔒 Forward Deployed Engineer Intern | Denver, CO | {LEVER_LINK} | Jun 28 |
    | Ramp | 🛂 Software Engineer Intern | New York, NY | {ASHBY_LINK} | Jun 20 |
    | Two Sigma | Data Scientist Intern | Remote | {TWOSIGMA_LINK} | 5d |
    | Ghost Corp | Analyst Intern | Nowhere |
    """
)

NO_TABLE = textwrap.dedent(
    """\
    # Summer 2027 Internships

    The table is being rebuilt. Check back soon.
    """
)

THIN_TABLE = textwrap.dedent(
    """\
    | Company | Role | Location | Application/Link | Date Posted |
    | --- | --- | --- | --- | --- |
    | Optiver | Quant Trader Intern | Austin, TX | [Apply](https://optiver.com/1) | Jul 02 |
    | IMC | SWE Intern | Chicago, IL | [Apply](https://imc.com/2) | Jul 01 |
    """
)

UNRECOGNISED_COLUMNS = textwrap.dedent(
    """\
    | Alpha | Beta | Gamma |
    | --- | --- | --- |
    | one | two | [Apply](https://x.com/1) |
    """
)


def make_connector(**overrides) -> MarkdownRepoConnector:
    kwargs = {"source_id": "vansh", "repo": "vanshb03/Summer2027-Internships"}
    return MarkdownRepoConnector(**{**kwargs, **overrides})


def fetch_document(connector: MarkdownRepoConnector, body: str):
    """Run the connector against a stubbed raw.githubusercontent.com response."""
    with respx.mock:
        respx.get(connector.url).mock(return_value=httpx.Response(200, text=body))
        with build_client() as client:
            return connector.fetch(client)


@pytest.fixture(scope="module")
def postings():
    return fetch_document(make_connector(), README)


class TestParsePostedDate:
    def test_month_day_without_year_resolves_to_this_year(self):
        assert parse_posted_date("Jul 09", today=TODAY) == datetime(2026, 7, 9, tzinfo=UTC)

    def test_future_looking_date_resolves_to_last_year(self):
        """``Dec 15`` read literally would be five months in the future; a
        posting cannot have been made before it existed, so it is last year's."""
        assert parse_posted_date("Dec 15", today=TODAY) == datetime(2025, 12, 15, tzinfo=UTC)

    def test_today_is_this_year_not_last(self):
        assert parse_posted_date("Jul 24", today=TODAY) == datetime(2026, 7, 24, tzinfo=UTC)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2026-03-01", datetime(2026, 3, 1, tzinfo=UTC)),
            ("Posted 2025-11-02", datetime(2025, 11, 2, tzinfo=UTC)),
        ],
    )
    def test_iso_dates_parse(self, value, expected):
        assert parse_posted_date(value, today=TODAY) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("5d", datetime(2026, 7, 19, tzinfo=UTC)),
            ("2mo", datetime(2026, 5, 25, tzinfo=UTC)),
            ("1 day", datetime(2026, 7, 23, tzinfo=UTC)),
            ("6h", datetime(2026, 7, 24, tzinfo=UTC)),
        ],
    )
    def test_age_strings_resolve_relative_to_today(self, value, expected):
        """speedyapply-style repos show "5d" rather than a date."""
        assert parse_posted_date(value, today=TODAY) == expected

    @pytest.mark.parametrize("value", ["", "   ", "N/A", "TBD", "—", "Rolling", None])
    def test_unparseable_values_return_none_rather_than_guessing(self, value):
        assert parse_posted_date(value, today=TODAY) is None

    def test_impossible_calendar_date_returns_none(self):
        assert parse_posted_date("Feb 30", today=TODAY) is None


class TestUrl:
    def test_points_at_the_raw_file(self):
        connector = make_connector(branch="dev", path="README.md")
        assert connector.url == (
            "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/README.md"
        )


class TestFetch:
    def test_returns_one_posting_per_usable_row(self, postings):
        assert [p.company_name for p in postings] == [
            "Jane Street",
            "Jane Street",
            "Citadel",
            "Palantir",
            "Ramp",
            "Two Sigma",
        ]

    def test_continuation_row_inherits_the_previous_company(self, postings):
        """``↳`` collapses consecutive roles at one firm. Reading it literally
        would strand a large share of rows under a meaningless company."""
        inherited = postings[1]
        assert inherited.company_name == "Jane Street"
        assert inherited.title == "Quantitative Trader Intern"
        assert inherited.url.endswith("gh_jid=8003020")

    def test_details_cell_becomes_separate_locations(self, postings):
        citadel = postings[2]
        assert citadel.locations_raw == ["New York, NY", "Greenwich, CT", "Miami, FL"]
        assert citadel.location_labels == ["Greenwich, CT", "Miami, FL", "New York, NY"]

    def test_closed_marker_deactivates_the_posting(self, postings):
        """🔒 means applications are shut; surfacing it as live wastes the
        operator's attention."""
        palantir = postings[3]
        assert palantir.is_active is False
        assert palantir.title == "Forward Deployed Engineer Intern"

    def test_open_rows_stay_active(self, postings):
        assert all(p.is_active for p in postings if p.company_name != "Palantir")

    def test_sponsorship_marker_is_carried_into_the_posting(self, postings):
        """🛂 is the only sponsorship signal these repos give."""
        ramp = postings[4]
        assert ramp.sponsorship_raw == "Does Not Offer Sponsorship"
        assert postings[0].sponsorship_raw is None

    def test_markers_are_stripped_from_the_title(self, postings):
        assert all("🔒" not in p.title and "🛂" not in p.title for p in postings)

    def test_malformed_row_is_skipped_without_raising(self, postings):
        """One bad row must not cost us the other four thousand."""
        assert "Ghost Corp" not in [p.company_name for p in postings]

    def test_dates_are_parsed_into_aware_datetimes(self, postings):
        assert all(p.posted_at is not None for p in postings)
        assert all(p.posted_at.tzinfo is not None for p in postings)

    def test_source_metadata_is_recorded(self, postings):
        assert postings[0].source_id == "vansh"
        assert postings[0].raw == {"repo": "vanshb03/Summer2027-Internships", "path": "README.md"}
        assert postings[0].employment_hint == "internship"


class TestDerivedFields:
    def test_company_and_title_are_canonicalised_for_dedup(self, postings):
        jane_street = postings[0]
        assert jane_street.canonical_company_name == "jane street"
        assert jane_street.normalized_title_value == "software engineer"

    def test_url_is_canonicalised_with_identity_params_kept(self, postings):
        """Stripping ``gh_jid`` would merge every Greenhouse role at a firm."""
        assert postings[0].canonical_url_value == (
            "https://boards.greenhouse.io/janestreet/jobs/8003019?gh_jid=8003019"
        )

    def test_ats_job_id_is_extracted_from_the_apply_url(self, postings):
        assert postings[0].ats_job_id == "8003019"
        assert postings[0].ats_vendor == "greenhouse"

    def test_every_posting_is_valid(self, postings):
        assert all(p.is_valid() for p in postings)


class TestLayoutGuards:
    def test_missing_table_is_a_connector_error(self):
        """Silence is indistinguishable from "no jobs"; the run must complain."""
        with pytest.raises(ConnectorError, match="no table rows found"):
            fetch_document(make_connector(), NO_TABLE)

    def test_too_few_usable_rows_is_a_connector_error(self):
        """A table that suddenly yields almost nothing means the file changed
        shape, not that the internship market collapsed."""
        with pytest.raises(ConnectorError, match="only 2 usable rows"):
            fetch_document(make_connector(), THIN_TABLE)

    def test_thin_table_is_accepted_when_the_threshold_allows_it(self):
        connector = make_connector(min_expected_rows=2)
        assert len(fetch_document(connector, THIN_TABLE)) == 2

    def test_unrecognised_columns_are_a_connector_error(self):
        with pytest.raises(ConnectorError, match="could not locate company/role"):
            fetch_document(make_connector(), UNRECOGNISED_COLUMNS)

    def test_http_failure_is_wrapped_as_a_connector_error(self):
        """One rotted source must not take the whole run down."""
        connector = make_connector()
        with respx.mock:
            respx.get(connector.url).mock(return_value=httpx.Response(404))
            with build_client() as client, pytest.raises(ConnectorError, match="fetch failed"):
                connector.fetch(client)
