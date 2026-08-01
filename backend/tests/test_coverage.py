"""Coverage answers "does adding this project help me?" with counts, so the
tests that matter are the ones pinning what a count is allowed to mean: a
posting is counted once no matter how many of a fact's terms it mentions,
unique reach really is the postings no *other* fact reaches, and the market view
never reports job-posting nouns as skills the operator is missing. The sample
size travels with every number, so it is asserted too.

Everything here is pure -- indexes are built from literal documents, and facts
are constructed in memory and never saved, because ``analyse`` only reads them.
"""

from uuid import uuid4

import pytest

from lighthouse.core.models import CorpusFact
from lighthouse.discover.coverage import MIN_MEANINGFUL_SAMPLE, MarketIndex, analyse

# A tiny market with a deliberate shape: "kubernetes" is the dominant skill and
# is central to one posting, "terraform" spans two, and "engineer" is the most
# frequent word of all while naming no skill at all.
MARKET = [
    "Platform engineer engineer engineer: Kubernetes Kubernetes Kubernetes Kubernetes Kubernetes",
    "Backend engineer engineer engineer: Kubernetes and Terraform",
    "Infrastructure engineer engineer engineer: Terraform and Ansible",
    "Data engineer engineer engineer: Python and Airflow",
    "Systems engineer engineer engineer: Rust and Go",
]


def _fact(title: str, body: str = "") -> CorpusFact:
    """An unsaved fact. ``analyse`` reads id/type/title/body and nothing else."""
    return CorpusFact(id=uuid4(), fact_type="project", title=title, body=body)


@pytest.fixture
def market():
    return MarketIndex(MARKET)


class TestMarketIndex:
    def test_counts_postings_and_core_postings_separately(self, market):
        """Two postings mention Kubernetes; only one leans on it hard enough to
        read as central, and conflating the two would overstate demand."""
        kubernetes = market.demand("kubernetes")
        assert (kubernetes.posting_count, kubernetes.core_count) == (2, 1)
        assert market.demand("terraform").core_count == 0

    def test_unknown_term_has_no_demand(self, market):
        assert market.demand("cobol") is None

    def test_reach_is_a_union_not_a_sum(self, market):
        """One posting mentions both terms. Counted twice it would inflate every
        reach figure a fact ever reports."""
        assert market.reach({"kubernetes", "terraform"}) == {0, 1, 2}

    def test_in_demand_omits_words_that_name_no_skill(self, market):
        """ "engineer" is the most frequent term in the sample and the least
        actionable. Reported as market demand it would be noise wearing the
        costume of insight."""
        terms = [d.term for d in market.in_demand()]
        assert "engineer" not in terms
        assert "kubernetes" in terms

    def test_in_demand_includes_general_vocabulary_when_asked(self, market):
        terms = [d.term for d in market.in_demand(skills_only=False)]
        assert terms[0] == "engineer"  # most postings, so it leads
        assert "kubernetes" in terms

    def test_in_demand_ranks_by_postings_and_respects_the_limit(self, market):
        top = market.in_demand(limit=2)
        assert [d.term for d in top] == ["kubernetes", "terraform"]

    @pytest.mark.parametrize(
        ("size", "expected"),
        [(MIN_MEANINGFUL_SAMPLE - 1, False), (MIN_MEANINGFUL_SAMPLE, True)],
    )
    def test_meaningful_sample_threshold(self, size, expected):
        assert MarketIndex(["Python role"] * size).is_meaningful is expected


class TestUniqueReach:
    """The headline metric: what a fact buys that nothing else in the corpus
    already buys. A fact whose terms are a subset of another's is real, useful
    experience and still adds no market reach -- saying so is the whole point."""

    def test_redundant_fact_reaches_nothing_of_its_own(self, market):
        redundant = _fact("Cluster migration", "Kubernetes")
        distinctive = _fact("Infra rebuild", "Kubernetes and Terraform")
        by_title = {c.title: c for c in analyse([redundant, distinctive], market).contributions}

        assert by_title["Cluster migration"].reach == 2
        assert by_title["Cluster migration"].unique_reach == 0
        assert by_title["Infra rebuild"].unique_reach == 1

    def test_a_lone_fact_owns_everything_it_reaches(self, market):
        only = analyse([_fact("Cluster migration", "Kubernetes")], market).contributions[0]
        assert only.unique_reach == only.reach == 2

    def test_fact_the_market_never_asks_for_is_still_listed(self, market):
        """Absence is the finding, so a fact that reaches nothing must stay
        visible rather than being filtered out of the report."""
        coverage = analyse([_fact("Woodworking", "Dovetail joinery")], market)
        contribution = coverage.contributions[0]
        assert contribution.reach == 0
        assert contribution.carries_market_weight is False


class TestAnalyse:
    def test_corpus_reach_deduplicates_across_facts(self, market):
        """Two facts both reaching posting 0 must not count it twice."""
        coverage = analyse(
            [_fact("Cluster migration", "Kubernetes"), _fact("Infra rebuild", "Terraform")], market
        )
        assert coverage.reached == 3
        assert coverage.unreached == 2

    def test_gaps_exclude_terms_the_corpus_evidences(self, market):
        coverage = analyse([_fact("Infra rebuild", "Kubernetes and Terraform")], market)
        terms = {g.term for g in coverage.gaps}
        assert not (terms & {"kubernetes", "terraform"})
        assert "rust" in terms

    def test_gaps_are_capped(self, market):
        assert len(analyse([], market, gap_limit=2).gaps) == 2

    def test_empty_corpus_reports_zero_rather_than_failing(self, market):
        """The first thing a new operator sees. Unioning an empty set of facts
        is the kind of edge case that raises instead of returning nothing."""
        coverage = analyse([], market)
        assert coverage.fact_count == 0
        assert coverage.contributions == []
        assert coverage.reached == 0
        assert coverage.gaps  # the market is still worth reporting

    def test_sample_travels_with_the_result(self, market):
        coverage = analyse([], market)
        assert coverage.sample_size == len(MARKET)
        assert coverage.is_meaningful is False


class TestBasis:
    """Every number is a count over a stated sample, so the sample is stated."""

    def test_states_the_sample_size(self):
        basis = analyse([], MarketIndex(["Python role"] * MIN_MEANINGFUL_SAMPLE)).basis()
        assert str(MIN_MEANINGFUL_SAMPLE) in basis
        assert "small sample" not in basis

    def test_small_sample_is_caveated(self, market):
        basis = analyse([], market).basis()
        assert str(len(MARKET)) in basis
        assert "small sample" in basis

    def test_no_postings_says_so(self):
        assert analyse([], MarketIndex([])).basis().startswith("No postings")
