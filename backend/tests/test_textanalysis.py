"""Text analysis is the whole evidence trail: every scored term traces to a
literal word here, so the tokeniser and stemmer must not lie about what a
posting said."""

import pytest

from lighthouse.core.textanalysis import (
    extract_phrases,
    is_technical,
    profile,
    stem,
    tokenize,
    tokenize_with_surface,
)


class TestTokenizeLiterals:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("C++", "c++"),
            ("CI/CD", "ci/cd"),
            (".NET", ".net"),
            ("Node.js", "node.js"),
        ],
    )
    def test_technical_punctuation_survives(self, text, expected):
        """Splitting "C++" on punctuation would erase the skill it names."""
        assert tokenize(text) == [expected]


class TestStem:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("engineering", "engineer"),
            ("deploying", "deployed"),
            ("scaling", "scaled"),
        ],
    )
    def test_inflections_collapse(self, a, b):
        """A posting saying "engineering" and a resume saying "engineer" are the
        same evidence and must share a comparison key."""
        assert stem(a) == stem(b)

    @pytest.mark.parametrize("word", ["kubernetes", "aws", "distributed", "redis"])
    def test_protected_terms_are_never_stemmed(self, word):
        """Stemming a technical name would break the match against it."""
        assert stem(word) == word


class TestStopwords:
    def test_dropped_by_default(self):
        assert "the" not in tokenize("the distributed system")

    def test_kept_when_requested(self):
        """Keyword tailoring sometimes needs the raw stream, stopwords and all."""
        assert "the" in tokenize("the distributed system", keep_stopwords=True)


class TestTokenizeCrumbs:
    @pytest.mark.parametrize(
        ("text", "crumb"),
        [
            ("U.S.", "u.s"),
            ("we'll", "ll"),
        ],
    )
    def test_short_nontechnical_crumbs_dropped(self, text, crumb):
        """Tokenisation debris reads as nonsense in a gap list."""
        assert crumb not in tokenize(text)

    @pytest.mark.parametrize("term", ["go", "r"])
    def test_short_technical_tokens_kept(self, term):
        """ "Go" and "R" are real skills despite being one or two letters."""
        assert term in tokenize(term)


class TestIsTechnical:
    @pytest.mark.parametrize("term", ["python", "kubernetes", "machine learning"])
    def test_recognised_vocabulary(self, term):
        assert is_technical(term) is True

    @pytest.mark.parametrize("term", ["opportunity", "team"])
    def test_general_words_rejected(self, term):
        assert is_technical(term) is False


class TestTokenizeWithSurface:
    def test_returns_stem_and_original_word(self):
        """The stem is a comparison key; the surface is what the operator is
        shown, so both must survive together."""
        pairs = tokenize_with_surface("distributing pipelines")
        assert ("distribut", "distributing") in pairs

    def test_surface_preserves_the_word_the_text_used(self):
        surfaces = {surface for _, surface in tokenize_with_surface("deployed to production")}
        assert "deployed" in surfaces


class TestProfile:
    def test_counts_repeated_terms(self):
        prof = profile("python python python go")
        assert prof.count("python") == 3
        assert prof.count("go") == 1

    def test_phrases_counted_as_their_own_term(self):
        """ "machine learning" twice is a specific ask that splitting into two
        words would lose."""
        prof = profile("machine learning research and machine learning models")
        assert prof.count("machine learning") == 2

    def test_display_returns_most_common_surface(self):
        prof = profile("Deployed and deployed and Deploying services")
        assert prof.display("deploy") == "deployed"

    def test_repeated_returns_terms_at_threshold_most_common_first(self):
        prof = profile("python python python go go rust")
        repeated = prof.repeated(2)
        assert repeated[0] == ("python", 3)
        assert ("go", 2) in repeated
        assert all(count >= 2 for _, count in repeated)

    def test_technical_terms_filters_to_technical(self):
        prof = profile("python python python mentorship mentorship mentorship")
        assert "python" in prof.technical_terms
        assert "mentorship" not in prof.technical_terms


class TestExtractPhrases:
    def test_finds_phrases_including_repeats(self):
        found = extract_phrases(
            "distributed systems and machine learning and machine learning again"
        )
        assert "distributed systems" in found
        assert found.count("machine learning") == 2
