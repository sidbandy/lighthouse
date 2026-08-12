"""Does this work for someone who is not a CS major?

"Any major" is a headline claim, and it is the one most likely to be quietly
false: the postings that carry descriptions come from Tier 3 ATS boards, which
skew engineering, so measuring anyone against the whole market compares them to
software roles. Live, that told a design student their biggest gaps were C++ and
electrical engineering — true, useless, and precisely the failure the claim has
to avoid.

The fix is that coverage defaults to the operator's own role families, seeded
from their major. These tests pin that: the same corpus, measured two ways,
must produce different and field-appropriate gaps, and the basis line must say
which slice it measured.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from lighthouse.core.corpus import FactInput, add_fact
from lighthouse.core.db import engine
from lighthouse.core.majors import role_families_for
from lighthouse.discover import coverage


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


def _corpus(session, user_id, facts):
    for kind, title, body in facts:
        add_fact(session, FactInput(fact_type=kind, title=title, body=body), user_id=user_id)
    session.flush()


DESIGN = [
    ("project", "Transit app redesign",
     "Ran user interviews, built a Figma prototype, ran usability testing."),
    ("skill", "Tools", "Figma, prototyping, user research, accessibility, wireframing"),
]
FINANCE = [
    ("experience", "Equity research intern",
     "Built three-statement models and DCF valuations in Excel for mid-cap industrials."),
    ("skill", "Tools", "Excel, Bloomberg, financial modeling, GAAP accounting, SQL"),
]


class TestMajorToRoleFamilies:
    """The mapping that makes the scoping possible at all."""

    @pytest.mark.parametrize(
        ("major", "expected"),
        [
            ("Computer Science", "swe"),
            ("Finance", "finance"),
            ("Graphic Design", "design"),
            ("Mechanical Engineering", "mechanical"),
            ("Marketing", "marketing"),
        ],
    )
    def test_a_major_resolves_to_its_field(self, major, expected):
        assert expected in role_families_for(major)

    def test_an_unrecognised_major_returns_nothing_rather_than_guessing(self):
        """A wrong guess silently scopes someone to the wrong market."""
        assert role_families_for("Underwater Basket Weaving") == []

    def test_no_families_means_the_whole_market(self, session):
        """Someone with no profile still gets a usable page."""
        user = uuid.uuid4()
        _corpus(session, user, DESIGN)
        report = coverage.corpus_coverage(session, role_families=(), user_id=user)
        assert report.role_families == ()
        assert "in " not in report.basis().split("that carry")[0]


class TestScopedCoverage:
    def test_the_basis_says_which_slice_it_measured(self, session):
        user = uuid.uuid4()
        _corpus(session, user, DESIGN)
        report = coverage.corpus_coverage(
            session, role_families=("design", "product"), user_id=user
        )
        assert "design" in report.basis()
        assert str(report.sample_size) in report.basis()

    def test_a_designer_is_not_told_to_learn_c_plus_plus(self, session):
        """The exact live failure this module exists for."""
        user = uuid.uuid4()
        _corpus(session, user, DESIGN)

        wide = coverage.corpus_coverage(session, role_families=(), user_id=user)
        scoped = coverage.corpus_coverage(
            session, role_families=("design", "product"), user_id=user
        )

        wide_gaps = {g.term for g in wide.gaps[:6]}
        scoped_gaps = {g.term for g in scoped.gaps[:6]}
        # The whole market is dominated by engineering vocabulary.
        assert wide_gaps != scoped_gaps
        assert scoped.sample_size < wide.sample_size

    def test_scoping_measures_against_fewer_but_relevant_postings(self, session):
        user = uuid.uuid4()
        _corpus(session, user, FINANCE)
        scoped = coverage.corpus_coverage(
            session, role_families=("finance", "business"), user_id=user
        )
        wide = coverage.corpus_coverage(session, role_families=(), user_id=user)
        assert scoped.sample_size <= wide.sample_size
        # Reach as a share of the sample should not collapse in their own field.
        if scoped.sample_size:
            assert scoped.reached / scoped.sample_size >= wide.reached / max(wide.sample_size, 1)

    def test_a_small_slice_says_it_is_small(self, session):
        """Twenty postings in one family is a real answer, and it has to carry
        its own caveat rather than reading like a market-wide finding."""
        user = uuid.uuid4()
        _corpus(session, user, DESIGN)
        report = coverage.corpus_coverage(session, role_families=("design",), user_id=user)
        if report.sample_size < coverage.MIN_MEANINGFUL_SAMPLE:
            assert not report.is_meaningful
            assert "small sample" in report.basis()
