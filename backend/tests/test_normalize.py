"""Normalisation is the only thing standing between three feeds and three rows.

Every connector funnels through this module, so a rule that is too aggressive
merges distinct roles and a rule that is too timid leaves the operator scrolling
past the same job three times.
"""

import pytest

from lighthouse.core.models import EmploymentType, RoleFamily, Sponsorship
from lighthouse.ingest.normalize import (
    canonical_company,
    canonical_url,
    classify_employment_type,
    classify_role_family,
    extract_ats,
    extract_job_id,
    location_label,
    normalize_title,
    parse_location,
    parse_sponsorship,
)


class TestCanonicalUrl:
    def test_preserves_gh_jid(self):
        """gh_jid *is* the job. Stripping it as a query parameter would collapse
        every Greenhouse role at a company onto one canonical URL."""
        url = "https://boards.greenhouse.io/optiver/jobs/8003019?gh_jid=8003019&utm_source=simplify"
        expected = "https://boards.greenhouse.io/optiver/jobs/8003019?gh_jid=8003019"
        assert canonical_url(url) == expected

    def test_two_greenhouse_roles_stay_distinct(self):
        base = "https://boards.greenhouse.io/optiver/jobs/embed?gh_jid="
        assert canonical_url(f"{base}8003019") != canonical_url(f"{base}8003020")

    @pytest.mark.parametrize(
        "tracking",
        [
            "utm_source=simplify",
            "utm_medium=email&utm_campaign=fall",
            "fbclid=IwAR123",
            "gclid=abc123",
            "ref=hackernews",
            "src=newsletter",
        ],
    )
    def test_strips_tracking_parameters(self, tracking):
        assert canonical_url(f"https://acme.com/jobs/9?{tracking}") == "https://acme.com/jobs/9"

    def test_lowercases_scheme_and_host_and_drops_www(self):
        assert canonical_url("HTTPS://WWW.Acme.COM/Jobs/9") == "https://acme.com/Jobs/9"

    def test_strips_trailing_slash_and_fragment(self):
        assert canonical_url("https://acme.com/jobs/9/#apply") == "https://acme.com/jobs/9"

    def test_parameter_order_does_not_change_identity(self):
        """Two feeds writing the same query in different orders must dedup."""
        first = canonical_url("https://acme.com/j?gh_jid=1&req_id=2")
        second = canonical_url("https://acme.com/j?req_id=2&gh_jid=1")
        assert first == second

    def test_adds_https_when_scheme_missing(self):
        assert canonical_url("acme.com/jobs/9") == "https://acme.com/jobs/9"

    def test_empty_in_empty_out(self):
        assert canonical_url("") == ""


class TestExtractJobId:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://boards.greenhouse.io/optiver/jobs/embed?gh_jid=8003019", "8003019"),
            ("https://jobs.lever.co/acme/1234567", "1234567"),
            (
                "https://jobs.ashbyhq.com/acme/3f2504e0-4f89-11d3-9a0c-0305e82c3301",
                "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
            ),
        ],
    )
    def test_extracts_identity_bearing_id(self, url, expected):
        assert extract_job_id(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "https://acme.com/careers/software-engineer-intern",
            "https://acme.com/jobs/42",
            "",
        ],
    )
    def test_returns_none_when_nothing_identifies_the_job(self, url):
        """A short numeric or slug segment is not an ATS id; inventing one would
        veto merges that should have happened."""
        assert extract_job_id(url) is None


class TestExtractAts:
    @pytest.mark.parametrize(
        ("url", "vendor"),
        [
            ("https://boards.greenhouse.io/optiver", "greenhouse"),
            ("https://careers.acme.com/apply?gh_jid=8003019", "greenhouse"),
            ("https://jobs.ashbyhq.com/acme", "ashby"),
            ("https://jobs.lever.co/acme", "lever"),
            ("https://acme.wd1.myworkdayjobs.com/en-US/External", "workday"),
            ("https://jobs.smartrecruiters.com/acme", "smartrecruiters"),
        ],
    )
    def test_detects_vendor(self, url, vendor):
        assert extract_ats(url) == vendor

    def test_unknown_host_returns_none(self):
        assert extract_ats("https://careers.acme.com/jobs/9") is None


class TestCanonicalCompany:
    def test_legal_suffix_and_case_do_not_split_a_company(self):
        """The blocking key is what lets dedup compare rows at all; if two
        spellings of Optiver produce two keys they are never even compared."""
        assert canonical_company("Optiver US, LLC ") == canonical_company("optiver us")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Acme Inc.", "acme"),
            ("Acme LLC", "acme"),
            ("Acme Ltd", "acme"),
            ("Acme Corp", "acme"),
            ("  Acme   Robotics  ", "acme robotics"),
            ("AT&T", "at and t"),
        ],
    )
    def test_reduces_to_the_discriminating_part(self, name, expected):
        assert canonical_company(name) == expected

    def test_different_companies_do_not_collide(self):
        """Merging two real companies is the expensive failure, so the rules are
        deliberately conservative."""
        assert canonical_company("Citadel") != canonical_company("Citadel Securities")
        assert canonical_company("Jane Street") != canonical_company("Jump Trading")


class TestNormalizeTitle:
    def test_season_and_intern_noise_collapse_to_the_same_role(self):
        """The season and the word "intern" vary per feed; the role does not."""
        seasoned = normalize_title("Software Engineer Intern, Summer 2027")
        plain = normalize_title("Software Engineering Intern")
        assert "software engineer" in seasoned
        assert "software engineer" in plain

    @pytest.mark.parametrize(
        "noise",
        ["Summer 2027", "Fall 2026", "Internship", "New Grad", "University Program"],
    )
    def test_drops_non_discriminating_tokens(self, noise):
        assert normalize_title(f"Quantitative Trader {noise}") == "quantitative trader"

    def test_drops_hyphenated_co_op(self):
        """A hyphenated co-op title must reduce to the same key as its intern
        twin, otherwise the two feeds spelling it either way never merge."""
        assert normalize_title("Quantitative Trader Co-op") == "quantitative trader"


class TestLocationParsing:
    def test_spelled_out_and_abbreviated_states_produce_one_label(self):
        """Two feeds spelling Illinois differently must merge into one city
        entry, otherwise the operator sees Chicago listed twice."""
        assert location_label(parse_location("Chicago, Illinois")) == "Chicago, IL"
        assert location_label(parse_location("Chicago, IL")) == "Chicago, IL"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("New York, NY +29", "New York, NY"),
            ("San Francisco, California +3 more", "San Francisco, CA"),
            ("Austin, TX (Hybrid)", "Austin, TX"),
        ],
    )
    def test_trailing_noise_does_not_block_state_extraction(self, raw, expected):
        assert location_label(parse_location(raw)) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("NYC", ("New York", "NY")),
            ("SF", ("San Francisco", "CA")),
            ("Bay Area", ("San Francisco", "CA")),
        ],
    )
    def test_shorthand_cities_resolve(self, raw, expected):
        parsed = parse_location(raw)
        assert (parsed["city"], parsed["state"]) == expected

    def test_remote_is_flagged_and_labelled(self):
        parsed = parse_location("Remote")
        assert parsed["is_remote"] is True
        assert location_label(parsed) == "Remote"

    def test_bare_state_name(self):
        parsed = parse_location("Texas")
        assert parsed["state"] == "TX"
        assert parsed["city"] is None

    def test_non_us_location_kept_raw_without_inventing_a_state(self):
        """A wrong state is worse than no state: it would make a London role
        filterable as a US one."""
        parsed = parse_location("London, UK")
        assert parsed["state"] is None
        assert parsed["raw"] == "London, UK"
        assert location_label(parsed) == "London, UK"

    def test_empty_input(self):
        parsed = parse_location("")
        assert parsed == {"city": None, "state": None, "raw": "", "is_remote": False}
        assert location_label(parsed) == ""


class TestClassifyRoleFamily:
    @pytest.mark.parametrize(
        ("title", "family"),
        [
            ("Quantitative Trader Intern", RoleFamily.QUANT),
            ("Machine Learning Engineer Intern", RoleFamily.AI_ML),
            ("Security Engineer Intern", RoleFamily.SECURITY),
            ("Data Scientist Intern", RoleFamily.DATA),
            ("FPGA Hardware Engineer Intern", RoleFamily.HARDWARE),
            ("Product Manager Intern", RoleFamily.PRODUCT),
            ("Software Engineer Intern", RoleFamily.SWE),
            ("Marketing Intern", RoleFamily.OTHER),
        ],
    )
    def test_buckets_by_keyword(self, title, family):
        assert classify_role_family(title) == family

    def test_specific_families_win_over_the_swe_catch_all(self):
        """An ML infra role is an ML role; matching "engineer" first would bury
        it in the largest bucket the operator already filters past."""
        assert classify_role_family("ML Infrastructure Engineer Intern") == RoleFamily.AI_ML


class TestClassifyEmploymentType:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Software Engineer Intern", EmploymentType.INTERNSHIP),
            ("Software Engineering Co-op", EmploymentType.INTERNSHIP),
            ("New Grad Software Engineer", EmploymentType.NEW_GRAD),
            ("Entry-Level Software Engineer", EmploymentType.NEW_GRAD),
            ("Staff Software Engineer", EmploymentType.OTHER),
        ],
    )
    def test_reads_the_title(self, title, expected):
        assert classify_employment_type(title) == expected

    @pytest.mark.parametrize(
        ("title", "hint", "expected"),
        [
            ("Software Engineer Intern", "new grad", EmploymentType.NEW_GRAD),
            ("Software Engineer", "internship", EmploymentType.INTERNSHIP),
        ],
    )
    def test_explicit_hint_beats_the_title(self, title, hint, expected):
        """A feed that states the type outright knows better than our keywords."""
        assert classify_employment_type(title, hint) == expected


class TestParseSponsorship:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("🛂", Sponsorship.DOES_NOT_OFFER),
            ("Does not offer sponsorship", Sponsorship.DOES_NOT_OFFER),
            ("No sponsorship provided", Sponsorship.DOES_NOT_OFFER),
            ("🇺🇸", Sponsorship.CITIZENSHIP_REQUIRED),
            ("U.S. Citizenship required", Sponsorship.CITIZENSHIP_REQUIRED),
            ("Offers sponsorship", Sponsorship.OFFERS),
            ("Will sponsor visas", Sponsorship.OFFERS),
        ],
    )
    def test_maps_feed_wording_onto_the_enum(self, raw, expected):
        assert parse_sponsorship(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "see job description"])
    def test_unknown_rather_than_a_guess(self, raw):
        """Sponsorship is a top-level filter; guessing wrong either wastes the
        operator's time or hides a role they were eligible for."""
        assert parse_sponsorship(raw) is Sponsorship.UNKNOWN
