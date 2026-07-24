"""Text analysis: tokenising, stemming, and finding the terms that matter.

Deliberately pure Python with no ML dependencies. That is not only a size
constraint -- it is the right tool for the job. Every term this module
surfaces is traceable to a literal word in the source text, so the operator can
always be shown *why* something scored the way it did. An embedding gives a
number nobody can argue with; a term count can be checked against the posting.

Three things live here:

* A tokeniser that understands technical writing, where ``C++``, ``.NET`` and
  ``CI/CD`` are single tokens rather than punctuation to discard.
* A light suffix stemmer, so "distributed"/"distributing" and
  "engineer"/"engineering" collapse together.
* A curated dictionary of technical terms and multi-word phrases, which is what
  separates "Kubernetes" from "opportunity" without a model.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# Tokens that survive as-is: technical writing is full of punctuation that is
# part of the name rather than a separator.
_LITERAL_TOKENS: frozenset[str] = frozenset(
    {
        "c++", "c#", ".net", "f#", "objective-c", "node.js", "next.js", "vue.js",
        "ci/cd", "tcp/ip", "a/b", "3d", "2d", "r&d", "c/c++",
    }
)  # fmt: skip

_LITERAL_RE = re.compile(
    "|".join(re.escape(t) for t in sorted(_LITERAL_TOKENS, key=len, reverse=True)),
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#._-]*[a-z0-9+#]|[a-z0-9]", re.IGNORECASE)

# Words carrying no signal about what a role requires. Includes job-posting
# boilerplate ("responsibilities", "qualifications"), which would otherwise
# dominate any frequency count.
STOPWORDS: frozenset[str] = frozenset(
    """
    a an the and or but if then else of in on at to for with without from by as is are was were be
    been being do does did doing have has had having will would shall should can could may might
    must this that these those it its they them their there here what which who whom whose when
    where why how all any both each few more most other some such no nor not only own same so than
    too very just also about above after again against before below between during into through
    under over up down out off further once you your yours we our ours us i me my mine he she his
    her him hers
    job role position opportunity opportunities candidate candidates applicant applicants
    responsibility responsibilities qualification qualifications requirement requirements
    description overview summary about apply application applying please note preferred plus
    nice must basic minimum required experience experiences skill skills ability abilities
    work working works team teams company companies business world class leading global
    innovative dynamic passionate exciting join looking seeking hire hiring career careers
    year years month months day days time full part new strong excellent good great best
    including include includes etc via across within per using use used uses help helping
    ensure ensuring provide providing support supporting build building develop developing
    design designing create creating manage managing lead leading drive driving deliver
    delivering collaborate collaborating partner partnering environment culture benefits
    salary compensation equal employer opportunity diversity inclusive veteran disability
    student students undergraduate graduate degree bachelor master phd university college
    intern internship co op summer fall winter spring program programme
    """.split()
)

# Curated technical vocabulary. This is the piece that lets a pure-lexical
# approach behave sensibly: it marks which tokens are real technical signal.
# Kept as a flat set of canonical forms; multi-word entries are matched as
# phrases before single tokens.
TECH_TERMS: frozenset[str] = frozenset(
    """
    python java javascript typescript golang go rust ruby scala kotlin swift php perl haskell
    ocaml elixir erlang clojure julia matlab fortran cobol assembly bash shell powershell
    c c++ c# .net objective-c r sql nosql
    react angular vue svelte nextjs nodejs express django flask fastapi rails spring dotnet
    jquery redux graphql rest grpc soap webpack vite babel tailwind bootstrap sass
    postgres postgresql mysql sqlite oracle mongodb cassandra redis dynamodb elasticsearch
    neo4j snowflake bigquery redshift clickhouse influxdb kafka rabbitmq activemq
    aws azure gcp kubernetes docker terraform ansible puppet chef jenkins gitlab github
    circleci travis argocd helm istio prometheus grafana datadog splunk pagerduty
    linux unix windows macos ios android embedded firmware rtos
    tensorflow pytorch keras scikit-learn sklearn pandas numpy scipy jupyter spark hadoop
    airflow dbt kubeflow mlflow huggingface transformers llm rag nlp
    git svn mercurial jira confluence figma
    verilog vhdl fpga asic pcb altium cadence synopsys spice
    api sdk cli gui orm mvc crud oauth jwt saml ldap ssl tls https ssh vpn
    agile scrum kanban devops sre mlops ci cd tdd bdd oop
    algorithm algorithms datastructure concurrency parallelism multithreading asynchronous
    microservices monolith serverless containerisation containerization virtualisation
    latency throughput scalability availability reliability observability telemetry
    cryptography encryption authentication authorization penetration firewall
    statistics probability regression classification clustering optimisation optimization
    derivatives equities futures options hedging arbitrage portfolio
    """.split()
)

# Multi-word phrases worth treating as one term. A posting saying "distributed
# systems" six times is asking for something quite specific, and splitting it
# into "distributed" + "systems" loses that.
TECH_PHRASES: tuple[str, ...] = (
    "machine learning",
    "deep learning",
    "reinforcement learning",
    "computer vision",
    "natural language processing",
    "large language models",
    "generative ai",
    "distributed systems",
    "operating systems",
    "computer architecture",
    "data structures",
    "data engineering",
    "data science",
    "data pipeline",
    "software engineering",
    "software development",
    "web development",
    "full stack",
    "front end",
    "back end",
    "backend development",
    "frontend development",
    "system design",
    "systems design",
    "object oriented",
    "functional programming",
    "version control",
    "unit testing",
    "integration testing",
    "test automation",
    "continuous integration",
    "continuous deployment",
    "code review",
    "cloud computing",
    "cloud infrastructure",
    "infrastructure as code",
    "high frequency trading",
    "quantitative research",
    "quantitative trading",
    "market making",
    "risk management",
    "time series",
    "signal processing",
    "embedded systems",
    "real time",
    "low latency",
    "high performance",
    "linear algebra",
    "discrete mathematics",
    "numerical methods",
    "database design",
    "query optimisation",
    "query optimization",
    "network security",
    "information security",
    "threat modeling",
    "threat modelling",
    "product management",
    "user experience",
    "technical writing",
)

_PHRASE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (phrase, re.compile(r"\b" + r"[\s-]+".join(map(re.escape, phrase.split())) + r"\b", re.I))
    for phrase in TECH_PHRASES
)

# Suffix rules, longest first. A real stemmer (Porter) over-stems for technical
# text -- it turns "kubernetes" into "kubernet" -- so this stays conservative
# and only strips inflections that genuinely matter here.
_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("ization", "ize"),
    ("isation", "ize"),
    ("ations", "ate"),
    ("ation", "ate"),
    ("ements", "ement"),
    ("ingly", ""),
    ("edly", ""),
    ("ements", "ement"),
    ("ments", "ment"),
    ("ities", "ity"),
    ("ives", "ive"),
    ("ing", ""),
    ("ers", "er"),
    ("ies", "y"),
    ("ied", "y"),
    ("ed", ""),
    ("es", ""),
    ("s", ""),
)

# Words that must never be stemmed: doing so would break a technical name.
_NO_STEM: frozenset[str] = frozenset(
    {"kubernetes", "aws", "css", "js", "ios", "as", "is", "has", "gas", "series", "analysis",
     "devops", "https", "tls", "ss", "less", "sass", "redis", "postgres", "keras", "pandas",
     "numpy", "scipy", "jenkins", "docs", "os", "hpc", "cs", "ds", "ml", "ai"}
)  # fmt: skip


def stem(word: str) -> str:
    """Collapse simple inflections. Conservative by design."""
    lowered = word.lower()
    if lowered in _NO_STEM or lowered in TECH_TERMS or len(lowered) <= 3:
        return lowered
    for suffix, replacement in _SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) - len(suffix) >= 3:
            return lowered[: -len(suffix)] + replacement
    return lowered


def tokenize_with_surface(text: str, *, keep_stopwords: bool = False) -> list[tuple[str, str]]:
    """Tokenise, returning ``(stem, surface_form)`` pairs.

    The surface form is kept because the stem is a comparison key, not
    something a human should ever be shown. Telling the operator to add
    "distribut" to their resume would be useless; "distributed" is the word the
    posting actually used.
    """
    if not text:
        return []

    lowered = text.lower()
    literals: list[str] = []

    def _capture(match: re.Match) -> str:
        literals.append(match.group(0))
        return " "

    remainder = _LITERAL_RE.sub(_capture, lowered)

    result: list[tuple[str, str]] = [(lit, lit) for lit in literals]
    for match in _WORD_RE.finditer(remainder):
        token = match.group(0)
        cleaned = token.strip("._-")
        if not cleaned or cleaned.isdigit():
            continue
        if not keep_stopwords and cleaned in STOPWORDS:
            continue
        stemmed = stem(cleaned)
        if not keep_stopwords and stemmed in STOPWORDS:
            continue
        if len(stemmed) >= 2 or stemmed in TECH_TERMS:
            result.append((stemmed, cleaned))
    return result


def tokenize(text: str, *, keep_stopwords: bool = False) -> list[str]:
    """Split text into comparable stems.

    Literal technical tokens (``C++``, ``CI/CD``) are extracted first so they
    survive; everything else is word-split, lowercased and stemmed.
    """
    return [s for s, _ in tokenize_with_surface(text, keep_stopwords=keep_stopwords)]


def extract_phrases(text: str) -> list[str]:
    """Multi-word technical phrases present in the text, with repeats kept."""
    if not text:
        return []
    found: list[str] = []
    for phrase, pattern in _PHRASE_PATTERNS:
        found.extend([phrase] * len(pattern.findall(text)))
    return found


def is_technical(term: str) -> bool:
    """Whether a term is recognised technical vocabulary."""
    return term in TECH_TERMS or term in TECH_PHRASES or stem(term) in TECH_TERMS


@dataclass(slots=True)
class TermProfile:
    """Term frequencies for one document, phrases included.

    ``counts`` is the raw evidence. Everything downstream -- match scores,
    keyword gaps, the resume tailor -- is derived from it, so the operator can
    always be shown the number behind a claim.
    """

    counts: Counter = field(default_factory=Counter)
    total_terms: int = 0
    # stem -> the surface form that appeared most often in the source text.
    surface: dict[str, str] = field(default_factory=dict)

    @property
    def terms(self) -> set[str]:
        return set(self.counts)

    @property
    def technical_terms(self) -> set[str]:
        return {t for t in self.counts if is_technical(t)}

    def count(self, term: str) -> int:
        return self.counts.get(term, 0)

    def display(self, term: str) -> str:
        """The human-readable form of a term."""
        return self.surface.get(term, term)

    def most_common(self, n: int = 20) -> list[tuple[str, int]]:
        return self.counts.most_common(n)

    def repeated(self, threshold: int) -> list[tuple[str, int]]:
        """Terms appearing at least ``threshold`` times, most frequent first.

        Repetition is the posting author telling you what they care about --
        this is the signal the keyword tailor is built on.
        """
        return [(t, c) for t, c in self.counts.most_common() if c >= threshold]


def profile(text: str) -> TermProfile:
    """Build a :class:`TermProfile` from raw text.

    Phrases are counted as their own terms *and* their component words are
    left in place, so "distributed systems" contributes to both the phrase and
    the general vocabulary. That double-count is intentional: a posting
    repeating the phrase really is weighting those words more heavily.
    """
    pairs = tokenize_with_surface(text)
    phrases = extract_phrases(text)

    counts = Counter(stemmed for stemmed, _ in pairs)
    counts.update(phrases)

    # Pick the most frequent surface form per stem, so "Distributed" and
    # "distributing" collapse to whichever the text actually favoured.
    variants: dict[str, Counter] = {}
    for stemmed, surface_form in pairs:
        variants.setdefault(stemmed, Counter())[surface_form] += 1
    surface = {stemmed: forms.most_common(1)[0][0] for stemmed, forms in variants.items()}
    surface.update({phrase: phrase for phrase in set(phrases)})

    return TermProfile(counts=counts, total_terms=len(pairs) + len(phrases), surface=surface)
