"""Matching's real output is the term breakdown, not the score. The tests that
matter are the ones proving a missing skill lands in `gaps` and a mere wording
difference does not -- because that distinction is what the operator acts on."""

import pytest

from lighthouse.discover.match import (
    CORE_THRESHOLD,
    IMPORTANT_THRESHOLD,
    CorpusIndex,
    MatchResult,
    TermMatch,
    build_index,
    coverage_score,
    match,
)

CORPUS = [
    "Built a distributed rate limiter in Python handling high throughput",
    "Python data pipeline for analytics with Python and SQL",
    "Automated deployment tooling written in Python",
]

# Python is well evidenced, "distributed" appears once, nothing else does.
POSTING = (
    "We use Python heavily. Python Python every day. "
    "You will work on distributed systems and distributed systems. "
    "Kubernetes Kubernetes Kubernetes experience is required. "
    "You will support customers customers customers customers directly. "
    "Rust is a plus."
)


@pytest.fixture
def index():
    return build_index(CORPUS)


class TestScore:
    def test_full_coverage_scores_high(self, index):
        result = match(
            title="Engineer",
            description="Python Python Python distributed distributed",
            index=index,
        )
        assert result.score >= 80

    def test_no_overlap_scores_zero(self, index):
        result = match(
            title="Engineer",
            description="Verilog Verilog VHDL FPGA Solidity blockchain",
            index=index,
        )
        assert result.score == 0

    def test_deterministic(self, index):
        a = match(title="Backend", description=POSTING, index=index)
        b = match(title="Backend", description=POSTING, index=index)
        assert (a.score, a.rarity) == (b.score, b.rarity)


class TestDescriptionAvailability:
    @pytest.mark.parametrize("description", [None, "", "   "])
    def test_false_without_description(self, index, description):
        result = match(title="Engineer", description=description, index=index)
        assert result.description_available is False

    def test_true_with_description(self, index):
        result = match(title="Engineer", description="Python role", index=index)
        assert result.description_available is True

    def test_thin_evidence_flagged_below_reliable_minimum(self, index):
        """A coverage ratio over one or two terms is arithmetically fine and
        practically meaningless, so it is flagged."""
        result = match(title="Engineer", description="Python role", index=index)
        assert result.terms_considered < MatchResult.MIN_RELIABLE_TERMS
        assert result.is_thin_evidence is True
        assert "weak evidence" in result.evidence_basis

    def test_full_evidence_not_flagged(self, index):
        result = match(title="Backend", description=POSTING, index=index)
        assert result.terms_considered >= MatchResult.MIN_RELIABLE_TERMS
        assert result.is_thin_evidence is False

    def test_title_only_evidence_basis(self, index):
        result = match(title="Python Engineer", description=None, index=index)
        assert result.evidence_basis == "title only - weak evidence"


class TestThreeBuckets:
    def test_matched_gap_and_wording_are_separated(self, index):
        result = match(title="Backend Engineer", description=POSTING, index=index)
        matched = {m.term for m in result.matched}
        gaps = {g.term for g in result.gaps}
        wording = {w.term for w in result.wording}

        assert "python" in matched
        assert "kubernetes" in gaps
        assert "distributed systems" in wording

    def test_wording_mismatch_carries_component_evidence(self, index):
        """The corpus says "distributed rate limiter"; the posting says
        "distributed systems". That is rewording, not a missing skill."""
        result = match(title="Backend Engineer", description=POSTING, index=index)
        entry = next(w for w in result.wording if w.term == "distributed systems")
        assert entry.component_evidence
        assert entry.is_wording_mismatch is True

    def test_unsupported_term_is_never_promoted(self, index):
        """A term with no corpus support must surface as a gap, not be hidden."""
        result = match(title="Backend Engineer", description=POSTING, index=index)
        rust = next(g for g in result.gaps if g.term == "rust")
        assert rust.corpus_count == 0
        assert rust.is_wording_mismatch is False

    def test_core_gaps_filter_by_emphasis(self, index):
        """ "Rust" is mentioned once, so it is a real gap but not a core one."""
        result = match(title="Backend Engineer", description=POSTING, index=index)
        assert all(g.posting_count >= IMPORTANT_THRESHOLD for g in result.core_gaps)
        assert "kubernetes" in {g.term for g in result.core_gaps}
        assert "rust" not in {g.term for g in result.core_gaps}

    def test_gaps_lead_with_technical(self, index):
        """ "customers" recurs more often than "kubernetes", but a missing skill
        is more actionable than a frequent generic word."""
        result = match(title="Backend Engineer", description=POSTING, index=index)
        assert result.gaps[0].is_technical is True
        kube = next(i for i, g in enumerate(result.gaps) if g.term == "kubernetes")
        customer = next(i for i, g in enumerate(result.gaps) if g.term == "customer")
        assert kube < customer


class TestEmptyCorpus:
    def test_is_empty(self):
        assert build_index([]).is_empty is True

    def test_every_match_scores_zero_without_error(self):
        index = build_index([])
        result = match(
            title="Engineer",
            description="Python Kubernetes distributed systems",
            index=index,
        )
        assert result.score == 0


class TestEmphasis:
    @pytest.mark.parametrize(
        ("posting_count", "expected"),
        [
            (CORE_THRESHOLD, "core"),
            (CORE_THRESHOLD + 1, "core"),
            (IMPORTANT_THRESHOLD, "important"),
            (IMPORTANT_THRESHOLD + 1, "important"),
            (IMPORTANT_THRESHOLD - 1, "mentioned"),
            (1, "mentioned"),
        ],
    )
    def test_thresholds(self, posting_count, expected):
        entry = TermMatch(
            term="kubernetes",
            display="Kubernetes",
            posting_count=posting_count,
            corpus_count=0,
            is_technical=True,
        )
        assert entry.emphasis == expected


class TestCoverageScore:
    def test_wording_mismatch_earns_half_credit(self):
        """The experience is real but a reader must make the leap, so it is not
        full credit."""
        matched = TermMatch("python", "Python", 3, 2, True)
        reworded = TermMatch(
            "distributed systems",
            "distributed systems",
            posting_count=3,
            corpus_count=0,
            is_technical=True,
            component_evidence=["distributed"],
        )
        assert coverage_score([matched]) == 100
        assert 0 < coverage_score([reworded]) < 100

    def test_empty_entries_score_zero(self):
        assert coverage_score([]) == 0


class TestCorpusIndex:
    def test_component_evidence_requires_all_distinctive_words(self):
        """ "risk management" is not vouched for by "management" alone."""
        index = build_index(["Managed a large distributed rate limiter"])
        assert index.component_evidence("distributed systems") == ["distributed"]
        assert index.component_evidence("risk management") == []

    def test_is_instance(self, index):
        assert isinstance(index, CorpusIndex)
