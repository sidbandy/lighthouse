"""Layers 2 and 3: was the answer structured, and was it true.

Layer 1 lives in ``delivery`` and never touches a model. These two do, behind
the provider layer, with a rule-based path that has to be good enough to ship
because it is what runs by default.

**The absolute constraint, from the spec and worth restating:** the feedback
engine reasons only about what was actually said. It never writes an improved
version of the operator's story, never fills in a detail that was not there, and
never invents project specifics. A coach that quietly fabricates part of your
own history is worse than no coach, because you would walk into the real
interview repeating something that is not true.

Layer 3 is the one that earns its place. Cross-referencing spoken claims against
the corpus catches "I led a team of five" when the corpus says three — a drift
that happens honestly, under pressure, and that a panel will find.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core import llm

# The four parts of a STAR answer, and the words people actually use to signal
# them. Detection is deliberately generous: the cost of missing a Result that
# was there is a wrong warning, which erodes trust in every other line.
_STAR_MARKERS: dict[str, tuple[str, ...]] = {
    "situation": (
        "we were", "at the time", "the context", "i was working", "our team",
        "the problem was", "we had", "during my", "when i",
    ),
    "task": (
        "i had to", "my job", "i was responsible", "my role", "i needed to",
        "the goal", "i was asked", "we needed",
    ),
    "action": (
        "i built", "i wrote", "i designed", "i implemented", "i decided",
        "so i ", "i started", "i changed", "i rewrote", "i proposed", "i led",
    ),
    "result": (
        "as a result", "in the end", "we shipped", "it reduced", "it improved",
        "we ended up", "the outcome", "which meant", "it went from", "we saw",
        "increased", "decreased", "saved", "cut ",
    ),
}

_STAR_LABELS = {
    "situation": "Situation",
    "task": "Task",
    "action": "Action",
    "result": "Result",
}

# A figure spoken in an answer. These are what Layer 3 checks, because they are
# the claims that are both checkable and repeated.
_NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?%?\b")


@dataclass(slots=True)
class StructureFinding:
    part: str
    label: str
    present: bool
    advice: str


@dataclass(slots=True)
class DriftFinding:
    """Something said that the corpus does not support."""

    claim: str
    detail: str


@dataclass(slots=True)
class AnswerFeedback:
    structure: list[StructureFinding] = field(default_factory=list)
    drift: list[DriftFinding] = field(default_factory=list)
    notes: str = ""
    provider: str = llm.Provider.RULE_BASED.value
    is_fallback: bool = False

    @property
    def missing(self) -> list[StructureFinding]:
        return [f for f in self.structure if not f.present]

    def summary(self) -> str:
        parts = []
        if self.missing:
            names = ", ".join(f.label for f in self.missing)
            parts.append(f"Missing: {names}.")
        else:
            parts.append("All four STAR parts are there.")
        if self.drift:
            parts.append(f"{len(self.drift)} claim(s) your corpus does not back.")
        return " ".join(parts)


def check_structure(transcript: str) -> list[StructureFinding]:
    """Which parts of STAR the answer actually contained.

    A missing Result is by far the most common failure, and the most costly:
    the interviewer is listening for what changed, and a story that stops at the
    action reads as effort without outcome.
    """
    text = " " + re.sub(r"\s+", " ", transcript.lower()) + " "
    advice = {
        "situation": "Open with one sentence of context — where, when, who.",
        "task": "Say what *you* were on the hook for, not what the team was.",
        "action": "The bulk of the answer. What did you personally do, and why that?",
        "result": (
            "The part that was missing. End with what changed — a number if you have "
            "one, and what you would do differently if you do not."
        ),
    }
    return [
        StructureFinding(
            part=part,
            label=_STAR_LABELS[part],
            present=any(marker in text for marker in markers),
            advice=advice[part],
        )
        for part, markers in _STAR_MARKERS.items()
    ]


def check_drift(transcript: str, sources: list[llm.SourceFact]) -> list[DriftFinding]:
    """Figures said out loud that the corpus does not contain.

    Reuses the same check the drafting layer uses, so "grounded" means one thing
    across the product. With an empty corpus it reports nothing rather than
    flagging everything — there is no drift from a record that does not exist.
    """
    if not sources:
        return []
    report = llm.verify_grounding(transcript, sources)
    return [
        DriftFinding(
            claim=number,
            detail=(
                f"You said {number}. Nothing in your corpus has that figure. Either the "
                "corpus is out of date or the number grew in the telling — worth settling "
                "before a real interview asks you to expand on it."
            ),
        )
        for number in report.unsupported_numbers
    ]


_SYSTEM = """You give feedback on one spoken interview answer.

Hard rules:
- Reason ONLY about what is in the transcript. Never add details, never invent
  project specifics, never write an improved version of their story.
- Three sentences maximum.
- Name one concrete thing to change next time.
- No praise-sandwiches and no scores.
"""


def _rule_based_notes(structure: list[StructureFinding], drift: list[DriftFinding]) -> str:
    missing = [f for f in structure if not f.present]
    if drift:
        return (
            "Before anything else, settle the figures: "
            f"{', '.join(d.claim for d in drift)} came up in the answer but not in your "
            "corpus. Interviewers follow up on numbers."
        )
    if not missing:
        return (
            "The shape is right — context, your part, what you did, what changed. "
            "Next run, try it once without notes and see whether the Result survives."
        )
    first = missing[0]
    return f"{first.advice} Everything else in the shape was there."


def build(
    transcript: str,
    *,
    sources: list[llm.SourceFact] | None = None,
    rubric: list[str] | None = None,
    provider: llm.LlmProvider | None = None,
) -> AnswerFeedback:
    """Structure, drift, and a sentence on what to change.

    ``rubric`` is a company's real evaluation criteria when Company Intelligence
    has them; without it the structural check is generic, which is stated rather
    than dressed up.
    """
    sources = sources or []
    structure = check_structure(transcript)
    drift = check_drift(transcript, sources)

    criteria = f"Score against these criteria: {', '.join(rubric)}.\n" if rubric else ""
    conversation = llm.Conversation(
        system=_SYSTEM,
        notes={"fallback": _rule_based_notes(structure, drift)},
    ).user(
        f"{criteria}"
        f"Parts present: {', '.join(f.label for f in structure if f.present) or 'none'}.\n"
        f"Parts missing: {', '.join(f.label for f in structure if not f.present) or 'none'}.\n"
        f"Transcript:\n{transcript}"
    )

    completion = llm.complete(conversation, sources=sources, provider=provider)
    notes = completion.text
    if sources and not completion.grounding.is_clean:
        # The model introduced a figure the transcript's own sources do not
        # support. Discard it and keep the deterministic note: feedback that
        # invents is the one failure this module cannot ship.
        notes = _rule_based_notes(structure, drift)

    return AnswerFeedback(
        structure=structure,
        drift=drift,
        notes=notes,
        provider=completion.provider.value,
        is_fallback=completion.is_fallback,
    )
