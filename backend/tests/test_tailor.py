"""Tailoring's job is honest reading: separate what a posting requires from what
it merely prefers, drop the EEO/benefits boilerplate every posting carries, and
sort each real requirement into evidenced / reword / genuine gap. The tests that
matter prove the boilerplate never surfaces as a "skill" and that a gap is named
as a gap, never smoothed into a keyword to invent."""

import pytest

from lighthouse.discover.match import build_index
from lighthouse.track.tailor import (
    Requirement,
    Tier,
    extract_hard_requirements,
    tailor,
)


@pytest.fixture
def index():
    """A corpus that evidences Go, Kubernetes and distributed work (under the
    operator's own wording, not the posting's phrase)."""
    return build_index(
        [
            "Built a distributed rate limiter in Go and deployed on Kubernetes",
            "Python data pipeline for analytics with Python and SQL",
        ]
    )


def _by_term(report):
    return {r.term: r for r in report.requirements}


class TestRequiredVsPreferred:
    def test_section_headings_set_the_tier(self, index):
        """A screen weights "required" far above "preferred", so the two
        sections must land in different tiers."""
        jd = "Requirements:\n- Python\n- Kubernetes\n\nPreferred Qualifications:\n- Rust\n"
        reqs = _by_term(tailor(title="Engineer", description=jd, index=index))

        assert reqs["python"].tier is Tier.REQUIRED
        assert reqs["kubernetes"].tier is Tier.REQUIRED
        assert reqs["rust"].tier is Tier.PREFERRED


class TestBoilerplateStripped:
    def test_eeo_footer_never_becomes_a_requirement(self, index):
        """The real bug this guards: EEO and benefits boilerplate clears any
        frequency bar, so left in it dominates the requirement list."""
        jd = (
            "Requirements:\n- Python and Kubernetes\n"
            "We are an equal opportunity employer. We provide reasonable "
            "accommodation on request. Protected veteran status is respected. "
            "The standard schedule is 40 hours per week.\n"
        )
        terms = {r.term for r in tailor(title="Engineer", description=jd, index=index).requirements}

        assert not (terms & {"accommodation", "veteran", "protected", "week"})
        assert {"python", "kubernetes"} <= terms  # the real requirements survive


class TestThreeBuckets:
    def test_evidenced_gap_and_reword_are_separated(self, index):
        """Corpus has Go and Kubernetes but not Rust; and it describes
        distributed work without the posting's exact phrase."""
        jd = (
            "Requirements:\n- Go and Kubernetes experience\n"
            "- Experience with distributed systems\n- Rust is required\n"
        )
        report = tailor(title="Engineer", description=jd, index=index)

        assert {"go", "kubernetes"} <= {r.term for r in report.evidenced}
        assert "rust" in {r.term for r in report.gaps}

    def test_wording_mismatch_is_a_reword_not_a_gap(self, index):
        """ "distributed systems" is evidenced under different wording, so telling
        the operator to go learn it would be wrong."""
        jd = "Requirements:\n- Experience with distributed systems\n- Rust is required\n"
        report = tailor(title="Engineer", description=jd, index=index)

        reword = next(r for r in report.rewords if r.term == "distributed systems")
        assert reword.component_evidence
        assert "distributed systems" not in {r.term for r in report.gaps}


class TestInResume:
    def test_evidenced_but_absent_from_resume_is_flagged(self, index):
        """The highest-leverage edit: something the operator can back up but did
        not put on the resume they actually sent."""
        jd = "Requirements:\n- Python\n- Kubernetes\n"
        report = tailor(
            title="Engineer",
            description=jd,
            index=index,
            resume_text="I built services in Python for years",
        )
        reqs = _by_term(report)

        assert reqs["python"].in_resume is True
        assert reqs["kubernetes"].evidenced is True
        assert reqs["kubernetes"].in_resume is False
        assert "kubernetes" in {r.term for r in report.missing_from_resume}


class TestHardRequirements:
    def test_finds_each_knockout_kind(self):
        """Years, degree, work authorization and graduation timing are the filters
        that reject before anyone reads the resume."""
        jd = (
            "Requirements:\n- 5+ years of experience in backend engineering\n"
            "- Bachelor's degree in CS or pursuing a degree\n"
            "- Must be authorized to work in the U.S.; U.S. citizen preferred\n"
            "- Graduating in 2027 or later\n"
        )
        kinds = {h.kind for h in extract_hard_requirements(jd)}

        assert {"experience", "degree", "authorization", "graduation"} <= kinds

    def test_boilerplate_hours_is_not_a_knockout(self):
        """ "40 hours per week" is benefits boilerplate, not a filter."""
        jd = "We are an equal opportunity employer working 40 hours per week.\n"
        hard = extract_hard_requirements(jd)

        assert all("week" not in h.detail.lower() for h in hard)
        assert all("hour" not in h.detail.lower() for h in hard)


class TestCoverage:
    def test_potential_is_never_below_coverage(self, index):
        jd = (
            "Requirements:\n- Go and Kubernetes experience\n"
            "- Experience with distributed systems\n- Rust is required\n"
        )
        report = tailor(title="Engineer", description=jd, index=index)
        assert report.potential_coverage() >= report.coverage()

    def test_fully_evidenced_posting_scores_100(self):
        idx = build_index(["Built services in Python and Go"])
        report = tailor(title="Engineer", description="Requirements:\n- Python\n- Go\n", index=idx)
        assert report.coverage() == 100

    def test_empty_requirements_score_zero_without_error(self, index):
        report = tailor(
            title="Engineer",
            description="We are an equal opportunity employer. Apply now.",
            index=index,
        )
        assert report.requirements == []
        assert report.coverage() == 0
        assert report.potential_coverage() == 0


class TestAdvice:
    def test_evidenced_but_not_on_resume_says_add_to_a_bullet(self):
        req = Requirement(
            term="python",
            display="Python",
            tier=Tier.REQUIRED,
            posting_count=3,
            is_technical=True,
            corpus_count=2,
            in_resume=False,
        )
        assert "inside a bullet" in req.advice()

    def test_reword_says_use_their_exact_wording(self):
        req = Requirement(
            term="distributed systems",
            display="distributed systems",
            tier=Tier.REQUIRED,
            posting_count=3,
            is_technical=True,
            corpus_count=0,
            component_evidence=["distributed"],
        )
        assert "exact wording" in req.advice()

    def test_genuine_gap_warns_against_inventing_a_keyword(self):
        req = Requirement(
            term="rust",
            display="Rust",
            tier=Tier.REQUIRED,
            posting_count=3,
            is_technical=True,
            corpus_count=0,
        )
        assert "keyword you cannot back up" in req.advice()


class TestCompanyNameFiltered:
    def test_company_name_is_not_a_requirement(self):
        """A JD repeats the company name constantly; without filtering it would
        top the requirement list, which is nonsense."""
        idx = build_index(["Python payments systems"])
        jd = (
            "At Stripe we build payments. Stripe engineers use Python. "
            "Stripe values Python. Join Stripe now."
        )
        report = tailor(title="Engineer", description=jd, index=idx, company_name="Stripe")

        assert "stripe" not in {r.term for r in report.requirements}
