"""The behavioural question bank, and picking what to ask next.

Questions are tagged with the same competencies the story bank uses, which is
what closes the loop: a competency with no story is a hole, and the question
that exposes it is the one worth practising. Without that link this would be a
list of prompts, which is a thing that already exists everywhere.

Selection prefers the competencies the operator has *not* covered, because a
mock that keeps asking about the story you have rehearsed is a mock that feels
good and teaches nothing.

One natural follow-up is attached to each. Real interviewers probe, and "what
was *your* specific contribution?" is the single most common follow-up and the
one people are least ready for -- so it is asked deterministically, not left to
a model that may or may not think of it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# The probe that follows almost every behavioural answer, and the reason a
# rehearsed story falls apart: it separates what the team did from what you did.
DEFAULT_FOLLOW_UP = "What was your specific contribution there, as opposed to the team's?"


@dataclass(frozen=True, slots=True)
class Question:
    text: str
    competency: str
    follow_up: str = DEFAULT_FOLLOW_UP


QUESTIONS: tuple[Question, ...] = (
    Question("Tell me about a time you took ownership of something outside your remit.",
             "ownership"),
    Question("Describe a project you saw through end to end. What would you do differently?",
             "ownership",
             "Which part of that was genuinely your call?"),
    Question("Tell me about a time you disagreed with someone on your team.", "conflict",
             "How did they describe the disagreement afterwards?"),
    Question("Describe a time you had to give someone difficult feedback.", "conflict"),
    Question("Tell me about a project where the requirements were unclear.", "ambiguity",
             "What made you confident enough to start?"),
    Question("Describe a time you had to make a decision without enough information.",
             "ambiguity"),
    Question("Tell me about a time something you built failed.", "failure",
             "What did you change so it could not happen the same way twice?"),
    Question("Describe the hardest bug you have chased. How did you find it?", "failure"),
    Question("Tell me about a time you led without any formal authority.", "leadership",
             "Why did they go along with it?"),
    Question("Describe a time you brought a group to a decision.", "leadership"),
    Question("Tell me about a time you had to choose what not to do.", "prioritization",
             "What did you say to the person whose work you deprioritised?"),
    Question("Describe how you handled competing deadlines.", "prioritization"),
    Question("Tell me about something technical you had to learn quickly.", "learning",
             "How did you know you actually understood it?"),
    Question("Describe a time you were the least experienced person in the room.", "learning"),
    Question("Tell me about the work you are most proud of. What changed because of it?",
             "impact",
             "How would you measure that if you had to defend the number?"),
    Question("Describe a time you improved something nobody asked you to improve.", "impact"),
    Question("Tell me about a time you worked with someone difficult.", "teamwork",
             "What did you do differently the second week?"),
    Question("Describe a time you had to rely on someone else's work.", "teamwork"),
)

QUESTIONS_BY_COMPETENCY: dict[str, list[Question]] = {}
for _q in QUESTIONS:
    QUESTIONS_BY_COMPETENCY.setdefault(_q.competency, []).append(_q)


def pick(
    *,
    uncovered_competencies: list[str] | None = None,
    competency: str | None = None,
    exclude: list[str] | None = None,
    rng: random.Random | None = None,
) -> Question:
    """Choose the next question to ask.

    Priority: an explicitly requested competency, then one the story bank does
    not cover, then anything. Practising the competency you already have a
    polished story for is the comfortable option and the useless one.
    """
    rng = rng or random.Random()
    seen = set(exclude or [])

    def _from(pool: list[Question]) -> Question | None:
        fresh = [q for q in pool if q.text not in seen]
        return rng.choice(fresh) if fresh else None

    if competency:
        chosen = _from(QUESTIONS_BY_COMPETENCY.get(competency, []))
        if chosen:
            return chosen

    for slug in uncovered_competencies or []:
        chosen = _from(QUESTIONS_BY_COMPETENCY.get(slug, []))
        if chosen:
            return chosen

    return _from(list(QUESTIONS)) or rng.choice(list(QUESTIONS))
