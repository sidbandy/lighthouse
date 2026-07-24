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
        "systems", "system", "learning", "management", "development", "engineering",
        "design", "programming", "computing", "processing", "analysis", "science",
        "structures", "testing", "integration", "control", "performance", "methods",
        "models", "end", "stack", "time", "oriented", "as", "code", "review",
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
    matched: list[TermMatch] = field(default_factory=list)
    gaps: list[TermMatch] = field(default_factory=list)
    wording: list[TermMatch] = field(default_factory=list)
    description_available: bool = True

    @property
    def core_gaps(self) -> list[TermMatch]:
        """Missing terms the posting leans on hardest. The actionable list."""
        return [t for t in self.gaps if t.posting_count >= IMPORTANT_THRESHOLD]

    @property
    def evidence_basis(self) -> str:
        """How much the score is worth, stated plainly.

        A match computed from a title alone is much weaker evidence than one
        computed from a full description, and the UI must be able to say so.
        """
        if not self.description_available:
            return "title only - weak evidence"
        return "full description"

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
            sum(d.total_terms for d in self.documents) / self.doc_count
            if self.doc_count
            else 0.0
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
        1 - BM25_B + BM25_B * (posting.total_terms / index.avg_length)
        if index.avg_length
        else 1.0
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


def _normalize(raw: float, posting: TermProfile) -> int:
    """Map a raw BM25 total onto 0-100.

    BM25 is unbounded, so the ceiling is derived from how much there was to
    match on: a short title cannot reach the same raw total as a full
    description, and scoring it against a fixed constant would make every
    title-only posting look poor.
    """
    if raw <= 0:
        return 0
    ceiling = max(8.0, math.sqrt(max(posting.total_terms, 1)) * 6.0)
    return max(0, min(100, round(100 * raw / (raw + ceiling))))


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

    raw = _bm25(posting, index)
    score = _normalize(raw, posting)

    matched: list[TermMatch] = []
    gaps: list[TermMatch] = []
    wording: list[TermMatch] = []

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
        if entry.matched:
            matched.append(entry)
        elif entry.is_wording_mismatch:
            wording.append(entry)
        else:
            gaps.append(entry)

    return MatchResult(
        score=score,
        matched=matched[:max_terms],
        gaps=gaps[:max_terms],
        wording=wording[:max_terms],
        description_available=bool(description and description.strip()),
    )
