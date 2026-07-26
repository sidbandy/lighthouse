"""Matching a posting against the operator's corpus.

The score is the *secondary* output. What actually changes behaviour is the
term-level breakdown: which of the posting's emphasised words the operator can
already evidence, and which they genuinely cannot. A number tells you a role is
a 62; a gap list tells you the posting says "Kubernetes" six times and your
corpus has never mentioned it, which is something you can act on.

Scoring uses BM25 over the corpus vocabulary, which is a well-understood
lexical ranking function with two useful properties here:

* **Saturation.** A posting repeating "Python" twenty times does not score
  twenty times higher than one mentioning it twice; the marginal value of each
  repeat falls away.
* **Rarity weighting.** Matching on "Verilog" is worth more than matching on
  "software", because the latter appears in nearly every posting.

Both are computed from counts we can show. Nothing here is a prediction, and
no term is ever recommended that the operator cannot already evidence -- the
gap list names missing skills, it does not suggest keywords to insert.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..core.textanalysis import TermProfile, is_technical, profile, stem

# Standard BM25 constants. k1 controls how fast term-frequency saturates; b
# controls how much document length is normalised away.
BM25_K1 = 1.2
BM25_B = 0.75

# Filler words inside technical phrases. They recur across dozens of unrelated
# phrases ("distributed systems", "operating systems", "system design"), so on
# their own they evidence nothing.
_GENERIC_PHRASE_WORDS: frozenset[str] = frozenset(
    {
        "systems",
        "system",
        "learning",
        "management",
        "development",
        "engineering",
        "design",
        "programming",
        "computing",
        "processing",
        "analysis",
        "science",
        "structures",
        "testing",
        "integration",
        "control",
        "performance",
        "methods",
        "models",
        "end",
        "stack",
        "time",
        "oriented",
        "as",
        "code",
        "review",
    }
)

# Repetition thresholds for the posting's own language. A term the author used
# three times is emphasised; five times is central to the role.
IMPORTANT_THRESHOLD = 3
CORE_THRESHOLD = 5


@dataclass(slots=True)
class TermMatch:
    """One term the posting emphasises, and whether the corpus evidences it.

    ``component_evidence`` carries the "phrasing to mirror" case: the posting
    says "distributed systems", the corpus never uses that exact phrase but does
    describe distributed work. That is not a skill gap -- it is a wording
    mismatch, and telling the operator to "learn distributed systems" when they
    have already done it would be wrong.
    """

    term: str
    display: str
    posting_count: int
    corpus_count: int
    is_technical: bool
    component_evidence: list[str] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return self.corpus_count > 0

    @property
    def is_wording_mismatch(self) -> bool:
        return self.corpus_count == 0 and bool(self.component_evidence)

    @property
    def emphasis(self) -> str:
        if self.posting_count >= CORE_THRESHOLD:
            return "core"
        if self.posting_count >= IMPORTANT_THRESHOLD:
            return "important"
        return "mentioned"


@dataclass(slots=True)
class MatchResult:
    """A posting scored against the corpus, with the evidence attached."""

    score: int
    # BM25 total. Not displayed -- it breaks ties between postings with equal
    # coverage by favouring the one matching on rarer terms.
    rarity: float = 0.0
    matched: list[TermMatch] = field(default_factory=list)
    gaps: list[TermMatch] = field(default_factory=list)
    wording: list[TermMatch] = field(default_factory=list)
    description_available: bool = True
    # How many signal terms the score was computed from. A coverage figure
    # derived from two terms is arithmetically fine and practically
    # meaningless, so the count travels with it.
    terms_considered: int = 0

    @property
    def core_gaps(self) -> list[TermMatch]:
        """Missing terms the posting leans on hardest. The actionable list."""
        return [t for t in self.gaps if t.posting_count >= IMPORTANT_THRESHOLD]

    # Below this, the score is reported but flagged: it is a ratio over too
    # small a base to mean anything.
    MIN_RELIABLE_TERMS = 6

    @property
    def is_thin_evidence(self) -> bool:
        return self.terms_considered < self.MIN_RELIABLE_TERMS

    @property
    def evidence_basis(self) -> str:
        """How much the score is worth, stated plainly.

        A match computed from a title alone is much weaker evidence than one
        computed from a full description, and a coverage ratio over a handful
        of terms is weaker still. The UI must be able to say both.
        """
        if not self.description_available:
            return "title only - weak evidence"
        if self.is_thin_evidence:
            return f"only {self.terms_considered} comparable terms - weak evidence"
        return f"full description, {self.terms_considered} terms compared"

    def summary(self) -> str:
        if not self.matched and not self.gaps:
            return "No comparable terms found"
        parts = [f"{len(self.matched)} terms evidenced"]
        if self.wording:
            parts.append(f"{len(self.wording)} to reword")
        gaps = len(self.core_gaps)
        parts.append(
            f"{gaps} emphasised term{'s' if gaps != 1 else ''} missing"
            if gaps
            else "no significant gaps"
        )
        return ", ".join(parts)


class CorpusIndex:
    """The operator's corpus, prepared for matching.

    Built once per scoring run and reused across every posting, which is what
    keeps scoring 26,000 rows cheap.
    """

    def __init__(self, documents: list[str]) -> None:
        self.documents = [profile(doc) for doc in documents if doc and doc.strip()]
        self.doc_count = len(self.documents)

        self.combined: TermProfile = profile(" \n ".join(documents))
        self.avg_length = (
            sum(d.total_terms for d in self.documents) / self.doc_count if self.doc_count else 0.0
        )
        # Document frequency drives rarity weighting.
        self.doc_freq: dict[str, int] = {}
        for doc in self.documents:
            for term in doc.terms:
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1

    @property
    def is_empty(self) -> bool:
        return self.doc_count == 0

    def idf(self, term: str) -> float:
        """Inverse document frequency, BM25 form.

        With a small personal corpus this is a coarse rarity signal, so it is
        floored at zero to stop common terms contributing negatively.
        """
        if self.doc_count == 0:
            return 0.0
        n = self.doc_freq.get(term, 0)
        return max(0.0, math.log(1 + (self.doc_count - n + 0.5) / (n + 0.5)))

    def count(self, term: str) -> int:
        return self.combined.count(term)

    def component_evidence(self, term: str) -> list[str]:
        """Corpus terms that evidence a multi-word phrase the corpus never
        spells out.

        The posting says "distributed systems"; the corpus says "distributed
        rate limiter". The concept is evidenced, the exact phrase is not. That
        distinction is the difference between telling the operator to reword
        something they have done and telling them to go learn it.
        """
        parts = term.split()
        if len(parts) < 2:
            return []

        # The distinctive words are what carry the meaning. "systems",
        # "learning" and "management" are filler that appear in dozens of
        # unrelated phrases, so evidencing them proves nothing on its own --
        # but evidencing "distributed" or "risk" does.
        distinctive = [p for p in parts if p not in _GENERIC_PHRASE_WORDS]
        if not distinctive:
            return []

        evidenced = [p for p in distinctive if self.combined.count(stem(p)) > 0]
        # Every distinctive word must be evidenced, so "risk management" is not
        # vouched for by "management" alone.
        return evidenced if len(evidenced) == len(distinctive) else []


def _bm25(posting: TermProfile, index: CorpusIndex) -> float:
    """BM25 of the posting's terms against the corpus."""
    if index.is_empty or posting.total_terms == 0:
        return 0.0

    length_norm = (
        1 - BM25_B + BM25_B * (posting.total_terms / index.avg_length) if index.avg_length else 1.0
    )

    total = 0.0
    for term, posting_count in posting.counts.items():
        corpus_count = index.count(term)
        if corpus_count == 0:
            continue
        # Technical terms carry more signal about fit than general vocabulary.
        weight = 1.5 if is_technical(term) else 1.0
        saturated = (corpus_count * (BM25_K1 + 1)) / (corpus_count + BM25_K1 * length_norm)
        total += index.idf(term) * saturated * weight * min(posting_count, CORE_THRESHOLD)
    return total


def _term_weight(term: str, posting_count: int) -> float:
    """How much a term counts toward the score.

    Repetition matters up to a point (the author saying "Kubernetes" five times
    means more than twice, but twenty times means no more than five), and
    technical vocabulary says more about fit than general English.
    """
    weight = float(min(posting_count, CORE_THRESHOLD))
    return weight * 1.5 if is_technical(term) else weight


def coverage_score(entries: list[TermMatch]) -> int:
    """Share of what the posting emphasises that the corpus can evidence.

    This *is* the score -- not a normalised BM25 total, which would be an
    arbitrary number scaled by an arbitrary constant. Coverage is directly
    interpretable ("you can evidence 40% of what this posting stresses"), it
    is reconstructable from the term lists shown alongside it, and it does not
    punish a posting merely for having a long description.

    Terms the operator has under different wording count as half credit: the
    experience is real, but a reader has to make the leap.
    """
    total = 0.0
    earned = 0.0
    for entry in entries:
        weight = _term_weight(entry.term, entry.posting_count)
        total += weight
        if entry.matched:
            earned += weight
        elif entry.is_wording_mismatch:
            earned += weight * 0.5
    if total <= 0:
        return 0
    return max(0, min(100, round(100 * earned / total)))


def build_index(documents: list[str]) -> CorpusIndex:
    return CorpusIndex(documents)


def match(
    *,
    title: str,
    description: str | None,
    index: CorpusIndex,
    max_terms: int = 12,
) -> MatchResult:
    """Score one posting and explain the result.

    ``matched`` and ``gaps`` are ordered by how heavily the posting leans on
    the term, so the top of each list is what matters most.
    """
    text = f"{title}\n{description}" if description else title
    posting = profile(text)

    matched: list[TermMatch] = []
    gaps: list[TermMatch] = []
    wording: list[TermMatch] = []
    considered: list[TermMatch] = []

    for term, posting_count in posting.counts.most_common():
        technical = is_technical(term)
        # General vocabulary is only interesting when the posting repeats it;
        # technical terms are interesting even mentioned once.
        if not technical and posting_count < IMPORTANT_THRESHOLD:
            continue
        # "You are missing: systems" is not something anyone can act on. These
        # words only carry meaning inside a phrase, which is reported separately.
        if term in _GENERIC_PHRASE_WORDS:
            continue
        entry = TermMatch(
            term=term,
            display=posting.display(term),
            posting_count=posting_count,
            corpus_count=index.count(term),
            is_technical=technical,
            component_evidence=index.component_evidence(term),
        )
        considered.append(entry)
        if entry.matched:
            matched.append(entry)
        elif entry.is_wording_mismatch:
            wording.append(entry)
        else:
            gaps.append(entry)

    # Lead the gap list with technical terms. A missing skill ("Kubernetes")
    # is actionable in a way a merely frequent word ("customers") is not, so it
    # should be what the operator sees first even if the generic word recurs
    # more often.
    gaps.sort(key=lambda t: (not t.is_technical, -t.posting_count))

    return MatchResult(
        score=coverage_score(considered),
        rarity=round(_bm25(posting, index), 2),
        terms_considered=len(considered),
        matched=matched[:max_terms],
        gaps=gaps[:max_terms],
        wording=wording[:max_terms],
        description_available=bool(description and description.strip()),
    )
