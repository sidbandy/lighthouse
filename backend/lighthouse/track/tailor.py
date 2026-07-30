"""Tailoring a resume to one specific posting.

The problem this solves: a generic resume matches 40-50% of any posting's
keywords; a tailored one matches 70-85%, and that gap is often the difference
between reaching a human and being filtered out. But tailoring by hand means
reading a job description closely enough to find *exactly* what they are asking
for -- which requirements are hard, which are nice-to-have, which words they
repeat -- and then honestly checking each against your own background.

This module does that reading. Given a posting and the operator's corpus it
produces, for this one posting:

* **What they require vs merely prefer.** The two are weighted very differently
  by a screen, so they are separated. "Must have / required / minimum" outranks
  "preferred / plus / nice-to-have".
* **Hard requirements and knockouts.** Years of experience, degree, work
  authorization, graduation timing -- the filters that reject before anyone
  reads a word.
* **Three honest buckets, prioritised.** Terms the resume already evidences;
  terms the operator *has* under different wording (mirror theirs); and genuine
  gaps -- named as gaps, never as keywords to invent.
* **Where to put each one.** A keyword inside a bullet describing a real
  achievement counts for more than the same word alone in a skills list, so the
  advice says which.

Nothing is fabricated. Every suggestion to add a term traces to a real corpus
fact; a term with no backing is reported as a real gap for the operator to
decide about, not smoothed over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum

from ..core.textanalysis import extract_phrases, is_technical, profile, stem, tokenize
from ..discover.match import CorpusIndex, TermMatch

IMPORTANT_THRESHOLD = 3
CORE_THRESHOLD = 5


class Tier(IntEnum):
    """How much a requirement matters to a screen. Ordered so higher is more
    important, and gaps sort worst-first."""

    REQUIRED = 3
    PREFERRED = 2
    RESPONSIBILITY = 1
    GENERAL = 0


# Section headings in a job description, mapped to the tier of what follows.
_SECTION_CUES: tuple[tuple[Tier, tuple[str, ...]], ...] = (
    (
        Tier.REQUIRED,
        (
            "requirements", "required qualifications", "minimum qualifications",
            "basic qualifications", "what you need", "what you'll need", "must have",
            "qualifications", "who you are", "what we're looking for", "you have",
        ),
    ),
    (
        Tier.PREFERRED,
        (
            "preferred qualifications", "preferred", "nice to have", "nice-to-have",
            "bonus", "bonus points", "pluses", "a plus", "ideally", "desired",
            "good to have", "extra credit", "stand out",
        ),
    ),
    (
        Tier.RESPONSIBILITY,
        (
            "responsibilities", "what you'll do", "what you will do", "the role",
            "your impact", "day to day", "day-to-day", "in this role", "about the role",
            "what you'll be doing",
        ),
    ),
)  # fmt: skip

# Sentence-level cues, used when a bullet has no section to sit under.
_REQUIRED_WORDS = re.compile(
    r"\b(must have|must be|required|require|minimum|at least|strong|proficient|"
    r"expert|deep (?:knowledge|understanding|experience)|solid)\b",
    re.IGNORECASE,
)
_PREFERRED_WORDS = re.compile(
    r"\b(preferred|nice to have|bonus|a plus|plus\b|ideally|desirable|"
    r"familiarity|exposure|helpful|good to have|would be great)\b",
    re.IGNORECASE,
)

# Legal, EEO and benefits boilerplate. Every posting carries this footer, and
# left in it dominates the requirement extraction -- "reasonable accommodation"
# and "protected veteran" are not skills, but they clear any frequency bar. Any
# sentence matching this is dropped before terms are counted.
_BOILERPLATE = re.compile(
    r"equal opportunity|reasonable accommodation|protected (?:veteran|status|class|characteristic)|"
    r"without regard to|regardless of race|gender identity|sexual orientation|"
    r"export control|export administration|background check|e-?verify|affirmative action|"
    r"base pay|salary range|pay range|compensation (?:range|package)|"
    r"committed to (?:diversity|building|creating|fostering)|disability status|"
    r"applicants with disabilities|drug (?:test|screen|free)|criminal histor|fair chance|"
    r"benefits (?:include|package|offered)|401\(?k\)?|paid time off|health insurance|"
    r"we are an|is an equal|hours per week|full[- ]time|part[- ]time position|"
    r"visa sponsorship|e\.?o\.?e\.?|veteran status|national origin|marital status|"
    r"accommodation.{0,20}(?:process|request|disabilit)|inclusive (?:workplace|environment)",
    re.IGNORECASE,
)


def _is_boilerplate(sentence: str) -> bool:
    return bool(_BOILERPLATE.search(sentence))


# Hard requirements: the knockouts. Each is a filter that rejects before a human
# reads the resume, so they are surfaced separately and prominently.
_HARD_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "experience",
        re.compile(r"\b(\d+)\+?\s*(?:-|to)?\s*\d*\+?\s*years?\b[^.\n]{0,40}experience", re.I),
        "Years of experience",
    ),
    (
        "degree",
        re.compile(
            r"\b(bachelor'?s?|master'?s?|ph\.?d|b\.?s\.?|m\.?s\.?|undergraduate|"
            r"graduate degree|pursuing|enrolled|currently studying)\b",
            re.I,
        ),
        "Degree requirement",
    ),
    (
        "authorization",
        re.compile(
            r"\b(u\.?s\.? citizen|security clearance|clearance|authorized to work|"
            r"work authorization|no sponsorship|not (?:able|provide) .{0,20}sponsor|"
            r"must be authorized)\b",
            re.I,
        ),
        "Work authorization",
    ),
    (
        "graduation",
        re.compile(r"\bgraduat\w+\b[^.\n]{0,30}\b(20\d{2})\b|\bclass of\s*(20\d{2})", re.I),
        "Graduation timing",
    ),
    (
        "location",
        # "must be located/based/on-site", but not "must be authorized" -- that
        # is an authorization knockout, and matching a bare "must be" here
        # double-counts it.
        re.compile(
            r"\b(on-?site|in-?office|relocat\w+|"
            r"must (?:reside|live|relocate|be (?:located|based|on-?site|in office)))\b",
            re.I,
        ),
        "Location / on-site",
    ),
)


@dataclass(slots=True)
class HardRequirement:
    kind: str
    label: str
    detail: str


@dataclass(slots=True)
class Requirement:
    """One thing the posting asks for, with how much it matters and whether the
    operator can evidence it."""

    term: str
    display: str
    tier: Tier
    posting_count: int
    is_technical: bool
    corpus_count: int
    component_evidence: list[str] = field(default_factory=list)
    in_resume: bool = False

    @property
    def evidenced(self) -> bool:
        return self.corpus_count > 0

    @property
    def is_reword(self) -> bool:
        return self.corpus_count == 0 and bool(self.component_evidence)

    @property
    def emphasis(self) -> str:
        if self.posting_count >= CORE_THRESHOLD:
            return "core"
        if self.posting_count >= IMPORTANT_THRESHOLD:
            return "important"
        return "mentioned"

    def advice(self) -> str:
        """The specific, honest next action for this requirement."""
        tier_word = {
            Tier.REQUIRED: "required",
            Tier.PREFERRED: "preferred",
            Tier.RESPONSIBILITY: "part of the role",
            Tier.GENERAL: "mentioned",
        }[self.tier]

        if self.evidenced and self.in_resume:
            return f"Already on your resume — good, this is {tier_word}."
        if self.evidenced and not self.in_resume:
            return (
                f"You have this in your corpus but it is not on the resume you sent. "
                f"Add it inside a bullet (a keyword in an achievement counts more than one "
                f"in a skills list). It is {tier_word}."
            )
        if self.is_reword:
            have = ", ".join(self.component_evidence)
            return (
                f"You have this — your corpus shows {have}. The posting says “{self.display}”; "
                f"use their exact wording so the screen matches it. It is {tier_word}."
            )
        if self.tier is Tier.REQUIRED:
            return (
                "Genuine gap on a required item. If you have any adjacent experience, surface "
                "it; if not, this is a real weakness for this posting — decide accordingly. "
                "Do not add a keyword you cannot back up."
            )
        return f"Not in your background. It is only {tier_word}, so this is lower risk."


@dataclass(slots=True)
class TailorReport:
    posting_title: str
    company_name: str | None
    hard_requirements: list[HardRequirement] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    resume_available: bool = True

    @property
    def evidenced(self) -> list[Requirement]:
        return [r for r in self.requirements if r.evidenced]

    @property
    def rewords(self) -> list[Requirement]:
        return [r for r in self.requirements if r.is_reword]

    @property
    def gaps(self) -> list[Requirement]:
        return [r for r in self.requirements if not r.evidenced and not r.is_reword]

    @property
    def required_gaps(self) -> list[Requirement]:
        return [r for r in self.gaps if r.tier is Tier.REQUIRED]

    @property
    def missing_from_resume(self) -> list[Requirement]:
        """Terms the operator can back up but did not put on the resume they
        sent. The highest-leverage edits: real, and quick to fix."""
        return [r for r in self.requirements if r.evidenced and not r.in_resume]

    def coverage(self) -> int:
        """Share of the posting's weighted requirements the operator can
        evidence. Reword counts half -- the experience is real, but a screen
        matching literal terms will not see it until the wording changes."""
        total = 0.0
        earned = 0.0
        for req in self.requirements:
            weight = float(req.tier + 1) * min(req.posting_count, CORE_THRESHOLD)
            total += weight
            if req.evidenced:
                earned += weight
            elif req.is_reword:
                earned += weight * 0.5
        return round(100 * earned / total) if total else 0

    def potential_coverage(self) -> int:
        """Coverage if the operator applied every honest edit -- surfaced
        corpus terms and adopted the posting's wording for things they have.
        The gap between this and coverage() is free, real improvement."""
        total = 0.0
        earned = 0.0
        for req in self.requirements:
            weight = float(req.tier + 1) * min(req.posting_count, CORE_THRESHOLD)
            total += weight
            if req.evidenced or req.is_reword:
                earned += weight
        return round(100 * earned / total) if total else 0

    def summary(self) -> str:
        cov, pot = self.coverage(), self.potential_coverage()
        parts = [f"You cover {cov}% of what this posting emphasises"]
        if pot > cov:
            parts.append(f"honest edits would bring it to ~{pot}%")
        req_gaps = len(self.required_gaps)
        if req_gaps:
            parts.append(
                f"{req_gaps} required item{'s' if req_gaps != 1 else ''} you cannot back up"
            )
        return "; ".join(parts) + "."


# --------------------------------------------------------------------------
# Job-description parsing
# --------------------------------------------------------------------------


def _split_sections(description: str) -> list[tuple[Tier, str]]:
    """Split a JD into (tier, text) blocks by its headings.

    Falls back to a single GENERAL block when the description has no recognisable
    structure, in which case sentence-level cues do the tier assignment.
    """
    lines = description.splitlines()
    blocks: list[tuple[Tier, list[str]]] = [(Tier.GENERAL, [])]

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        heading_tier = _heading_tier(line)
        if heading_tier is not None:
            blocks.append((heading_tier, []))
        else:
            blocks[-1][1].append(line)

    return [(tier, "\n".join(body)) for tier, body in blocks if body]


def _heading_tier(line: str) -> Tier | None:
    """If this line is a section heading, the tier of what follows it."""
    # Headings are short and often bold/colon-terminated; guard against matching
    # a full sentence that merely contains the word "requirements".
    normalized = line.rstrip(":").strip().lower()
    if len(normalized) > 45 or len(normalized.split()) > 6:
        return None
    for tier, cues in _SECTION_CUES:
        if any(normalized == cue or normalized.startswith(cue) for cue in cues):
            return tier
    return None


def _sentence_tier(sentence: str, section_tier: Tier) -> Tier:
    """Refine a sentence's tier using inline cues.

    A "preferred" word inside a requirements section demotes that line, and vice
    versa -- JDs mix the two constantly.
    """
    if _PREFERRED_WORDS.search(sentence):
        return Tier.PREFERRED
    if _REQUIRED_WORDS.search(sentence) and section_tier < Tier.REQUIRED:
        return Tier.REQUIRED
    return section_tier


def extract_hard_requirements(description: str) -> list[HardRequirement]:
    """The knockout filters, surfaced with the exact phrase that triggered them."""
    # Drop boilerplate lines first, so "40 hours per week" and visa-policy
    # sentences do not register as knockouts.
    clean = "\n".join(ln for ln in description.splitlines() if not _is_boilerplate(ln))
    found: list[HardRequirement] = []
    seen: set[str] = set()
    for kind, pattern, label in _HARD_PATTERNS:
        match = pattern.search(clean)
        if match and kind not in seen:
            seen.add(kind)
            snippet = " ".join(match.group(0).split())
            found.append(HardRequirement(kind=kind, label=label, detail=snippet))
    return found


def _collect_terms(description: str) -> dict[str, tuple[Tier, int, str]]:
    """Map each requirement term to its best (most important) tier, its count,
    and a display form.

    A term appearing in both a required and a preferred sentence takes the
    stronger tier, since that is how a screen would weight it.
    """
    result: dict[str, tuple[Tier, int, str]] = {}

    for section_tier, body in _split_sections(description):
        for sentence in re.split(r"[.\n•]|(?:^|\s)[-*]\s", body):
            sentence = sentence.strip()
            if not sentence or _is_boilerplate(sentence):
                continue
            tier = _sentence_tier(sentence, section_tier)
            prof = profile(sentence)
            for term, count in prof.counts.items():
                technical = is_technical(term)
                # General words only count when the sentence is a real
                # requirement line; technical terms always count.
                if not technical and tier < Tier.RESPONSIBILITY:
                    continue
                display = prof.display(term)
                existing = result.get(term)
                new_count = (existing[1] if existing else 0) + count
                best_tier = max(tier, existing[0]) if existing else tier
                result[term] = (best_tier, new_count, display)

    return result


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

# Filler that is never a useful requirement even when it clears the frequency
# bar. Mirrors the generic-phrase words in match.py.
_STOP_REQUIREMENTS = {
    "systems",
    "system",
    "team",
    "work",
    "ability",
    "experience",
    "knowledge",
    "understanding",
    "strong",
    "years",
    "role",
    "company",
    "world",
    "using",
    "related",
    "field",
    "similar",
    "including",
    "etc",
    "environment",
    # Boilerplate survivors and generic verbs that clear the frequency bar.
    "week",
    "hour",
    "reasonable",
    "accommodation",
    "protected",
    "require",
    "internet",
    "technology",
    "export",
    "benefit",
    "opportunity",
    "candidate",
    "applicant",
    "employer",
    "status",
    "process",
    "position",
    "internship",
    "intern",
    "program",
    "day",
    "month",
    "year",
    "people",
    "person",
    # Eligibility/authorization words -- surfaced as knockouts, not skills.
    "eligible",
    "eligibility",
    "authorized",
    "authorization",
    "citizen",
    "citizenship",
    "clearance",
    "sponsorship",
    "visa",
    "degree",
    "gpa",
    "graduate",
    "graduation",
    "enrolled",
    "pursuing",
}


def tailor(
    *,
    title: str,
    description: str,
    index: CorpusIndex,
    resume_text: str | None = None,
    company_name: str | None = None,
    max_terms: int = 30,
) -> TailorReport:
    """Produce the full tailoring report for one posting."""
    report = TailorReport(
        posting_title=title,
        company_name=company_name,
        hard_requirements=extract_hard_requirements(description),
        resume_available=bool(resume_text and resume_text.strip()),
    )

    # What the resume the operator actually sent contains, so we can tell "you
    # have it" from "you have it and it is already on the resume".
    resume_terms: set[str] = set()
    if resume_text:
        resume_terms = {stem(t) for t in tokenize(resume_text)}
        resume_terms |= set(extract_phrases(resume_text))

    company_terms = {stem(t) for t in tokenize(company_name or "")}

    requirements: list[Requirement] = []
    for term, (tier, count, display) in _collect_terms(description).items():
        if term in _STOP_REQUIREMENTS or term in company_terms:
            continue
        technical = is_technical(term)
        # Keep every technical term, but a general word must be genuinely
        # emphasised to be worth the operator's attention.
        if not technical and count < IMPORTANT_THRESHOLD:
            continue
        requirements.append(
            Requirement(
                term=term,
                display=display,
                tier=tier,
                posting_count=count,
                is_technical=technical,
                corpus_count=index.count(term),
                component_evidence=index.component_evidence(term),
                in_resume=term in resume_terms,
            )
        )

    # Order by what matters most: tier first, then how hard the posting leans on
    # it, then technical terms ahead of general vocabulary.
    requirements.sort(key=lambda r: (-r.tier, -r.posting_count, not r.is_technical))
    report.requirements = requirements[:max_terms]
    return report


def term_to_match(req: Requirement) -> TermMatch:
    """Adapt a Requirement to the TermMatch shape the discover UI already
    knows, so the two surfaces render identically."""
    return TermMatch(
        term=req.term,
        display=req.display,
        posting_count=req.posting_count,
        corpus_count=req.corpus_count,
        is_technical=req.is_technical,
        component_evidence=req.component_evidence,
    )
