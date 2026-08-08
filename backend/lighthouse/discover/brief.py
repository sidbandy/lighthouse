"""Pulls the decision-relevant facts out of a job description.

Pay, working pattern, length, deadline, GPA floor, named interview stages and
the lines describing the work. Everything is extracted rather than inferred,
and each fact carries the sentence it came from so a bad parse is visible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------

# A currency amount: $25, $25.50, $100,000, $150K, £40,000, €50k, CAD 60,000.
_AMOUNT = r"(?:\$|US\$|USD\s?|CAD\s?|C\$|CA\$|£|€|₹)\s?\d[\d,]*(?:\.\d{1,2})?\s*[KkMm]?\b"

# The unit tells you whether 25 is an hourly rate or an annual insult.
_RATE_UNIT = (
    r"(?:per\s+hour|/\s?hour|/\s?hr\b|an\s+hour|hourly|"
    r"per\s+year|/\s?year|/\s?yr\b|annually|annualized|annual|per\s+annum|"
    r"per\s+month|/\s?month|monthly|per\s+week|/\s?week|weekly)"
)

_COMPENSATION_RE = re.compile(
    rf"({_AMOUNT})(?:\s*(?:-|–|—|to|and)\s*({_AMOUNT}))?\s*(?:\(?\s*({_RATE_UNIT})\s*\)?)?",
    re.I,
)

# Words that make a dollar figure a *pay* figure. Without one of these nearby,
# "$2M in savings" in a bullet about impact would be reported as the salary.
_PAY_CONTEXT = re.compile(
    r"\b(salary|salaries|compensation|pay|paid|rate|wage|stipend|base|"
    r"hourly|remuneration|earn|offer[s]? between|range)\b",
    re.I,
)

_UNIT_LABEL: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"hour|/\s?hr", re.I), "per hour"),
    (re.compile(r"year|annum|annual", re.I), "per year"),
    (re.compile(r"month", re.I), "per month"),
    (re.compile(r"week", re.I), "per week"),
)


# --------------------------------------------------------------------------
# Everything else worth pulling out
# --------------------------------------------------------------------------

# "3.0 GPA", "GPA of 3.5", "a minimum cumulative average of 3.2", and the
# trailing forms -- "3.0 or above", "3.5 and higher" -- which are common enough
# that missing them loses a real knockout.
_GPA_RE = re.compile(
    r"\b(?:minimum\s+|min\.?\s+|at least\s+|a\s+)?"
    r"(?:(?:cumulative\s+|overall\s+)?(?:gpa|grade\s+point\s+average|average)"
    r"\s*(?:of|:|is|above|at\s+least)?\s*(\d\.\d{1,2})"
    r"|(\d\.\d{1,2})\s*(?:\+|/\s*4(?:\.0)?)?\s*"
    r"(?:or\s+(?:above|higher|better)|and\s+(?:above|higher))?\s*"
    r"(?:cumulative\s+)?(?:gpa|grade\s+point\s+average))",
    re.I,
)

_DURATION_RE = re.compile(
    r"\b(\d{1,2})\s*[-–]?\s*(week|month)s?\b[^.\n]{0,30}?"
    r"(?:internship|program|co-?op|placement|assignment)"
    r"|(?:internship|program|co-?op)\b[^.\n]{0,30}?\b(\d{1,2})\s*[-–]?\s*(week|month)s?\b",
    re.I,
)

# Every branch requires application context. A bare "deadline" must not match:
# "thrives under tight deadlines" is a soft-skills bullet on a large minority of
# postings, and reporting it as this posting's closing date is worse than
# reporting no date at all.
_DEADLINE_RE = re.compile(
    r"\b(?:"
    r"appl(?:y|ication|ications)\s+(?:by|before|due|close[sd]?|closing|"
    r"will\s+close|must\s+be\s+(?:submitted|received))"
    r"|(?:application|submission|priority|early)\s+deadlines?\s*(?:is|are|:)?"
    r"|deadlines?\s+(?:to|for)\s+appl(?:y|ying|ication|ications)"
    r"|last\s+day\s+to\s+apply"
    r"|accepting\s+applications\s+(?:until|through)"
    r")[^.\n]{0,60}",
    re.I,
)

# Interview stages a posting names outright. Each maps to a plain label, because
# "HackerRank" and "CodeSignal" are the same fact to someone deciding how to
# prepare: there is a timed automated round.
_PROCESS_STEPS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Online assessment",
        re.compile(
            r"\b(online assessment|\bOA\b|hackerrank|codility|codesignal|karat|"
            r"coding challenge|take-?home|technical screen(?:ing)?)\b",
            re.I,
        ),
    ),
    ("Phone screen", re.compile(r"\b(phone screen|recruiter (?:call|screen)|intro call)\b", re.I)),
    (
        "Behavioural interview",
        re.compile(r"\b(behavio(?:u)?ral|competency|values interview|STAR)\b", re.I),
    ),
    ("Case study", re.compile(r"\b(case study|case interview|business case)\b", re.I)),
    (
        "Onsite / final round",
        re.compile(r"\b(on-?site interview|final round|super\s?day|panel interview)\b", re.I),
    ),
    (
        "Portfolio review",
        re.compile(r"\b(portfolio review|portfolio submission|design review)\b", re.I),
    ),
)

_ARRANGEMENT: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Fully remote",
        re.compile(r"\b(fully remote|100% remote|remote[- ]first|work from home)\b", re.I),
    ),
    ("Hybrid", re.compile(r"\bhybrid\b", re.I)),
    ("On-site", re.compile(r"\b(on-?site|in-?office|in person)\b", re.I)),
)

_DAYS_IN_OFFICE_RE = re.compile(
    r"\b(\d|one|two|three|four|five)\s*(?:\+\s*)?days?\s*(?:per|a|/)\s*week\b[^.\n]{0,25}"
    r"|(?:in (?:the )?office|on-?site)[^.\n]{0,20}\b(\d|one|two|three|four|five)\s*days?\b",
    re.I,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(slots=True)
class Fact:
    """One extracted fact, with the sentence it came from.

    Regexes over free prose are wrong often enough that a figure needs to be
    checkable against its source.
    """

    kind: str
    label: str
    value: str
    evidence: str


@dataclass(slots=True)
class PostingBrief:
    """The decision-relevant contents of one job description."""

    compensation: Fact | None = None
    gpa: Fact | None = None
    duration: Fact | None = None
    deadline: Fact | None = None
    arrangement: Fact | None = None
    process: list[Fact] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)

    @property
    def logistics(self) -> list[Fact]:
        """The single-value facts that exist, in the order they are read in."""
        return [
            f
            for f in (self.compensation, self.arrangement, self.duration, self.deadline, self.gpa)
            if f is not None
        ]

    @property
    def is_thin(self) -> bool:
        """True when the description said almost nothing concrete.

        Worth surfacing: a posting that names no pay, no dates and no process is
        not a posting the operator can evaluate, and that absence is itself
        information about the employer.
        """
        return not self.logistics and not self.process


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _quote(sentence: str, limit: int = 220) -> str:
    """One tidy line of evidence."""
    collapsed = " ".join(sentence.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def _normalise_amount(raw: str) -> str:
    return " ".join(raw.split()).replace(" ", "")


# Below this, an amount with no stated unit is almost certainly not the pay --
# a bonus differential, a fee, a price. Real rates name their unit.
_MIN_UNITLESS_AMOUNT = 1000.0


def _numeric(raw: str) -> float:
    """The figure inside a currency string, with K/M expanded."""
    digits = re.search(r"\d[\d,]*(?:\.\d+)?", raw)
    if not digits:
        return 0.0
    value = float(digits.group(0).replace(",", ""))
    suffix = raw.strip()[-1:].lower()
    return value * {"k": 1_000, "m": 1_000_000}.get(suffix, 1)


def extract_compensation(sentences: list[str]) -> Fact | None:
    """The stated pay, if the posting states any.

    Requires either an explicit rate unit ("$25 per hour") or a pay word in the
    same sentence. A bare dollar figure in a bullet about impact is not a
    salary, and reporting it as one would be worse than reporting nothing.
    """
    for sentence in sentences:
        match = _COMPENSATION_RE.search(sentence)
        if not match:
            continue
        low, high, unit = match.group(1), match.group(2), match.group(3)
        if not unit and not _PAY_CONTEXT.search(sentence):
            continue
        # Postings routinely separate the amount from its unit -- "$25.00 USD
        # Hourly", "the annual base salary is $120,000" -- so when nothing sits
        # directly after the figure, take the unit from elsewhere in the same
        # sentence. Without this the most useful part of the most useful field
        # is dropped on a large minority of postings.
        if not unit:
            nearby = re.search(_RATE_UNIT, sentence, re.I)
            unit = nearby.group(0) if nearby else None

        # A tiny unqualified figure in a sentence that merely contains the word
        # "pay" is not the pay: "$2 increase in pay" would otherwise be reported
        # as the salary. A real rate always names its unit.
        if not unit and _numeric(low) < _MIN_UNITLESS_AMOUNT:
            continue

        value = _normalise_amount(low)
        if high:
            value += f"–{_normalise_amount(high)}"
        if unit:
            label = next(
                (lbl for pattern, lbl in _UNIT_LABEL if pattern.search(unit)), unit.lower()
            )
            value += f" {label}"
        return Fact("compensation", "Pay", value, _quote(sentence))
    return None


def extract_gpa(sentences: list[str]) -> Fact | None:
    """The stated GPA floor, on the 4.0 scale the eligibility check assumes.

    Postings from other systems quote other scales -- "a current GPA of 8.00" is
    a 10-point scale, and rendering it as a GPA requirement beside US postings
    invites exactly the wrong conclusion. Out-of-scale figures are dropped
    rather than converted, because the posting never said which scale it meant.
    """
    for sentence in sentences:
        match = _GPA_RE.search(sentence)
        if match:
            value = match.group(1) or match.group(2)
            if not 1.0 <= float(value) <= 4.0:
                continue
            return Fact("gpa", "GPA requirement", value, _quote(sentence))
    return None


def extract_duration(sentences: list[str]) -> Fact | None:
    for sentence in sentences:
        match = _DURATION_RE.search(sentence)
        if match:
            number = match.group(1) or match.group(3)
            unit = match.group(2) or match.group(4)
            return Fact("duration", "Length", f"{number} {unit}s", _quote(sentence))
    return None


def extract_deadline(sentences: list[str]) -> Fact | None:
    for sentence in sentences:
        match = _DEADLINE_RE.search(sentence)
        if match:
            return Fact("deadline", "Deadline", _quote(match.group(0), 90), _quote(sentence))
    return None


def extract_arrangement(sentences: list[str]) -> Fact | None:
    """Remote, hybrid or on-site, with the days-per-week if stated.

    Ordered most-specific first: a posting saying "hybrid, 3 days on-site"
    matches both "hybrid" and "on-site", and hybrid is the truer answer.
    """
    for label, pattern in _ARRANGEMENT:
        for sentence in sentences:
            if not pattern.search(sentence):
                continue
            days = _DAYS_IN_OFFICE_RE.search(sentence)
            value = label
            if days:
                value += f" · {' '.join(days.group(0).split())}"
            return Fact("arrangement", "Working pattern", value, _quote(sentence))
    return None


def extract_process(sentences: list[str]) -> list[Fact]:
    """Interview stages the posting names. Only what it says, in reading order."""
    found: list[Fact] = []
    seen: set[str] = set()
    for sentence in sentences:
        for label, pattern in _PROCESS_STEPS:
            if label in seen:
                continue
            match = pattern.search(sentence)
            if match:
                seen.add(label)
                found.append(
                    Fact("process", label, " ".join(match.group(0).split()), _quote(sentence))
                )
    return found


# Lines that open a duty rather than describing the company or the benefits.
_DUTY_START = re.compile(
    r"^(?:you(?:'ll| will)?\s+|we(?:'re| are)? looking|help\s|work\s|build\s|design\s|develop\s|"
    r"support\s|analy[sz]e\s|create\s|maintain\s|collaborate\s|contribute\s|assist\s|"
    r"conduct\s|research\s|test\s|write\s|own\s|drive\s|partner\s|manage\s|lead\s)",
    re.I,
)


def extract_responsibilities(sentences: list[str], limit: int = 6) -> list[str]:
    """The lines that describe the actual work.

    A crude filter on purpose: sentences that open with a duty verb, are long
    enough to say something and short enough to be a bullet rather than a
    paragraph of company history. Getting one wrong costs the operator a glance;
    the alternative — an LLM summary — costs the guarantee that every word on
    screen came from the posting.
    """
    picked: list[str] = []
    for sentence in sentences:
        clean = " ".join(sentence.split()).lstrip("•-–—*· ")
        if not (40 <= len(clean) <= 240):
            continue
        if not _DUTY_START.match(clean):
            continue
        picked.append(clean if len(clean) <= 200 else clean[:199] + "…")
        if len(picked) >= limit:
            break
    return picked


# Weeks in a year, for prorating an annualised figure over a stated internship
# length. Deliberately the naive number: the point is a rough second reading of
# a real quoted figure, not a payroll calculation.
_WEEKS_PER_YEAR = 52


def _prorated(compensation: Fact, duration: Fact) -> Fact:
    """Add "~$48k over 10 weeks" beside an annualised figure.

    Quant firms quote interns an annualised base -- "Base Salary: $250,000" for
    a ten-week internship -- which the brief reports verbatim and correctly, and
    which reads as absurd. The stated figure is never replaced: this adds a
    second reading of the same real number, and only when the posting itself
    supplied both halves.
    """
    if "per year" not in compensation.value:
        return compensation
    weeks_match = re.match(r"(\d+)\s+weeks?", duration.value)
    if not weeks_match:
        return compensation

    weeks = int(weeks_match.group(1))
    if not 1 <= weeks < _WEEKS_PER_YEAR:
        return compensation

    amount = re.search(r"\$([\d,]+(?:\.\d+)?)", compensation.value)
    if not amount:
        return compensation
    annual = float(amount.group(1).replace(",", ""))
    over_term = annual * weeks / _WEEKS_PER_YEAR
    rendered = f"${over_term / 1000:.0f}k" if over_term >= 1000 else f"${over_term:.0f}"
    return replace(
        compensation,
        value=f"{compensation.value} · ~{rendered} over {weeks} weeks",
    )


def build(description: str | None) -> PostingBrief:
    """Read one description into a brief. Empty in, empty out."""
    if not description or not description.strip():
        return PostingBrief()

    sentences = _sentences(description)
    compensation = extract_compensation(sentences)
    duration = extract_duration(sentences)
    if compensation and duration:
        compensation = _prorated(compensation, duration)

    return PostingBrief(
        compensation=compensation,
        gpa=extract_gpa(sentences),
        duration=duration,
        deadline=extract_deadline(sentences),
        arrangement=extract_arrangement(sentences),
        process=extract_process(sentences),
        responsibilities=extract_responsibilities(sentences),
    )
