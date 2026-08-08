"""Company identity: the blocking key, and healing rows written under an old one.

Getting this wrong is quiet and expensive. ``canonical_company`` is both the
dedup blocking key and the lookup key for the selectivity table, so a name that
normalises two ways produces two company rows, each holding half the postings,
each able to miss its tier -- which is how an elite quant firm ends up in the
Target lane labelled "a realistic match at a realistic bar".

Because the key is *derived* from the display name, drift is detectable, and
``reconcile_companies`` is what makes a change to the normalisation safe to
deploy against a database that already has rows in it.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from lighthouse.core.db import engine
from lighthouse.core.models import Company, Posting
from lighthouse.discover.lanes import SEED_TIERS
from lighthouse.ingest.normalize import canonical_company
from lighthouse.ingest.pipeline import reconcile_companies


@pytest.fixture
def session():
    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)
    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()


def _company(session, name: str) -> Company:
    company = Company(name=name, canonical_name=canonical_company(name))
    session.add(company)
    session.flush()
    return company


def _split_company(session) -> tuple[Company, Company]:
    """One company sitting under two keys, which is what a change to the
    normalisation leaves behind. Names are unique so the real database's
    companies cannot collide with the fixture."""
    name = f"Fixture Quant {uuid4().hex[:12]}"
    keeper = _company(session, name)
    stray = Company(name=name, canonical_name=f"stale key {uuid4().hex[:8]}")
    session.add(stray)
    session.flush()
    return keeper, stray


def _posting(session, company: Company) -> Posting:
    slug = uuid4().hex[:12]
    posting = Posting(
        company_id=company.id,
        title="Quant Trader Intern",
        normalized_title="quant trader",
        url=f"https://example.com/{slug}",
        canonical_url=f"https://example.com/{slug}",
    )
    session.add(posting)
    session.flush()
    return posting


class TestCanonicalCompany:
    def test_initialisms_rejoin(self):
        """Punctuation stripping splits "D. E. Shaw" into single letters, which
        then misses a tier table keyed on "de shaw"."""
        assert canonical_company("D. E. Shaw") == "de shaw"
        assert canonical_company("J.P. Morgan") == "jp morgan"
        assert canonical_company("H.B. Fuller") == "hb fuller"

    def test_dangling_conjunction_is_dropped(self):
        """"& Co." leaves an "and" behind once the suffix is stripped."""
        assert canonical_company("D.E. Shaw & Co.") == "de shaw"
        assert canonical_company("Eli Lilly and Company") == "eli lilly"

    def test_aliases_reach_what_normalisation_cannot(self):
        assert canonical_company("IMC") == canonical_company("IMC Trading")
        assert canonical_company("Facebook") == canonical_company("Meta Platforms Inc.")
        assert canonical_company("Optiver US, LLC") == "optiver"

    def test_suffix_stripping_never_eats_the_whole_name(self):
        """"H&CO" is a company, not the letter H with a suffix. A one-character
        key blocks against everything it meets."""
        assert canonical_company("H&CO") == "h and co"
        assert len(canonical_company("H&CO")) > 1

    def test_distinct_companies_stay_distinct(self):
        assert canonical_company("Citadel") != canonical_company("Citadel Securities")
        assert canonical_company("Meta") != canonical_company("Meta Materials")

    @pytest.mark.parametrize(
        "name", ["D. E. Shaw", "IMC", "Optiver US, LLC", "Jane Street Capital"]
    )
    def test_elite_firms_resolve_to_their_tier(self, name):
        """The failure this whole module exists to prevent: an elite firm
        falling through to the mid default and landing in Target."""
        assert SEED_TIERS.get(canonical_company(name)) == "elite"


class TestReconcileCompanies:
    def test_rekeys_a_row_whose_key_is_stale(self, session):
        company = _company(session, "Some Fixture Firm")
        company.canonical_name = "stale key that no longer derives"
        session.flush()

        reconcile_companies(session)

        assert company.canonical_name == canonical_company("Some Fixture Firm")

    def test_merges_two_rows_for_one_company(self, session):
        """The IMC case: one company under two keys because the normalisation
        changed between the two writes. Postings split, so "seen on N lists"
        undercounts and either row can miss its tier."""
        keeper, stray = _split_company(session)
        _posting(session, keeper)
        stray_posting = _posting(session, stray)
        stray_id = stray.id

        merged = reconcile_companies(session)
        session.flush()

        assert merged == 1
        assert session.get(Company, stray_id) is None
        assert stray_posting.company_id == keeper.id

    def test_carries_over_details_from_the_row_it_removes(self, session):
        keeper, stray = _split_company(session)
        stray.ats_vendor = "greenhouse"
        stray.ats_slug = "fixture"
        stray.careers_url = "https://example.com/careers"
        session.flush()

        reconcile_companies(session)

        assert keeper.ats_vendor == "greenhouse"
        assert keeper.ats_slug == "fixture"
        assert keeper.careers_url == "https://example.com/careers"

    def test_is_idempotent(self, session):
        keeper, _ = _split_company(session)
        _posting(session, keeper)

        assert reconcile_companies(session) == 1
        session.flush()
        assert reconcile_companies(session) == 0

    def test_leaves_correct_rows_alone(self, session):
        company = _company(session, "Fixture Analytics")
        before = company.canonical_name

        assert reconcile_companies(session) == 0
        assert company.canonical_name == before
        assert session.scalar(select(Company).where(Company.id == company.id)) is company
