"""Regression: wanting a company must never change how hard it is to get into.

``companies.tier`` once carried two unrelated facts at once -- selectivity
(elite/high/mid/accessible) and "the operator marked this a target", written as
``tier='target'``. Because 'target' resolved to mid selectivity, marking Jane
Street demoted it from 4 to 2, which moved it out of Reach and into Target: the
app telling an applicant that an elite quant firm is "a realistic match at a
realistic bar". Targeting now lives in ``operator_targets`` -- a personal table,
because wanting a company is a fact about the operator and not about the company
-- and ``tier`` means selectivity only.

The tests below hold that separation from both ends -- the write must not touch
``tier``, and the lane the operator finally sees must not move.

DB tests run in a transaction rolled back afterwards and scope to a fresh
user_id, so real company rows and the real operator's targets are untouched."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from lighthouse.core.db import engine
from lighthouse.core.models import Company
from lighthouse.core.onboarding import (
    set_target_companies,
    target_companies,
    target_company_count,
)
from lighthouse.discover.lanes import (
    TIER_ELITE,
    Lane,
    assign_lane,
    selectivity_of,
)
from lighthouse.ingest.normalize import canonical_company

ELITE_NAME = "Jane Street"


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


@pytest.fixture
def user_id():
    """A user of our own, so these tests never see or disturb the real
    operator's targets."""
    return uuid4()


def _seed_company(session, name: str) -> Company:
    """A row for a company the seed tier table knows, with no explicit tier.

    Reuses the ingested row when one already exists -- ``canonical_name`` is
    unique, and the point of the test is the seed-table path either way.
    """
    company = session.scalar(
        select(Company).where(Company.canonical_name == canonical_company(name))
    )
    if company is None:
        company = Company(name=name, canonical_name=canonical_company(name))
        session.add(company)
    company.tier = None
    session.flush()
    return company


def _is_target(session, company: Company, user_id) -> bool:
    return company.id in {c.id for c in target_companies(session, user_id=user_id)}


def _new_company(session, *, tier: str | None = None) -> Company:
    """A company the real data cannot already contain, so counts are exact."""
    name = f"Fixture Co {uuid4().hex[:10]}"
    company = Company(name=name, canonical_name=canonical_company(name), tier=tier)
    session.add(company)
    session.flush()
    return company


class TestSelectivity:
    def test_seed_table_applies_when_no_tier_is_stored(self):
        """Nothing writes a tier for most companies, so the seed table is the
        only thing keeping elite firms in Reach."""
        assert selectivity_of("jane street", None) == 4

    def test_target_is_not_a_selectivity_tier(self):
        """The value that caused the bug is gone from the tier table, so a row
        left over from before falls back to the honest unknown default rather
        than reading as a deliberate mid rating."""
        assert selectivity_of("unknown co", "target") == 2

    def test_stored_tier_overrides_the_seed_table(self):
        assert selectivity_of("jane street", "accessible") == 1


class TestMarkingTargets:
    def test_marking_a_target_does_not_touch_selectivity(self, session, user_id):
        company = _seed_company(session, ELITE_NAME)
        set_target_companies(session, [ELITE_NAME], user_id=user_id)

        assert _is_target(session, company, user_id)
        assert company.tier is None
        assert selectivity_of(company.canonical_name, company.tier) == 4

    def test_marked_elite_company_still_lands_in_reach(self, session, user_id):
        """End to end, which is where the operator actually saw the bug: a
        strong match on solid evidence at an elite firm is still a reach."""
        _seed_company(session, ELITE_NAME)
        set_target_companies(session, [ELITE_NAME], user_id=user_id)

        company = session.scalar(
            select(Company).where(Company.canonical_name == canonical_company(ELITE_NAME))
        )
        assignment = assign_lane(
            match_score=90,
            selectivity=selectivity_of(company.canonical_name, company.tier),
            thin_evidence=False,
        )
        assert assignment.lane is Lane.REACH
        # Selectivity 2 is what the old tier='target' write produced, and it is
        # exactly the wrong answer for Jane Street.
        assert assign_lane(match_score=90, selectivity=2, thin_evidence=False).lane is Lane.TARGET

    def test_unknown_name_gets_a_row_of_its_own(self, session, user_id):
        """A target the job lists have not surfaced yet is still tracked."""
        name = f"Fixture Co {uuid4().hex[:10]}"
        assert set_target_companies(session, [name], user_id=user_id) == 1

        created = session.scalar(
            select(Company).where(Company.canonical_name == canonical_company(name))
        )
        assert _is_target(session, created, user_id)
        assert created.tier is None

    def test_replace_clears_the_previous_selection(self, session, user_id):
        """Deselecting in the UI has to actually deselect, or the three-lane
        view keeps showing companies the operator dropped."""
        old = _new_company(session)
        new = _new_company(session)
        set_target_companies(session, [old.name], user_id=user_id)
        set_target_companies(session, [new.name], user_id=user_id)

        assert not _is_target(session, old, user_id)
        assert _is_target(session, new, user_id)

    def test_replace_false_adds_to_the_selection(self, session, user_id):
        old = _new_company(session)
        new = _new_company(session)
        set_target_companies(session, [old.name], user_id=user_id)
        set_target_companies(session, [new.name], replace=False, user_id=user_id)

        assert {c.id for c in target_companies(session, user_id=user_id)} == {old.id, new.id}

    def test_one_operators_targets_are_not_anothers(self, session, user_id):
        """The whole reason targeting is a personal table: marking a company
        must not mark it for everyone."""
        company = _new_company(session)
        set_target_companies(session, [company.name], user_id=user_id)

        assert target_company_count(session, user_id=uuid4()) == 0

    def test_count_counts_targets_not_tiers(self, session, user_id):
        """Selectivity is not interest: a tiered company nobody marked is not a
        target, and onboarding's "pick targets" step depends on that."""
        tiered = _new_company(session, tier=TIER_ELITE)
        assert target_company_count(session, user_id=user_id) == 0

        set_target_companies(session, [tiered.name], user_id=user_id)
        assert target_company_count(session, user_id=user_id) == 1
