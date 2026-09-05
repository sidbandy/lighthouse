"""Rendering the digest.

Plain text, because this is read on a phone lock screen at 7am and the only
thing that matters is whether it is worth opening the laptop for. Every line
carries the fact behind it -- the score, what the score was computed from, and
the terms the posting wants that the corpus does not have -- so the decision
can be made from the message rather than from the app.
"""

from __future__ import annotations

from datetime import date

from .selection import AlertCandidate

GHOST_NOTE = {
    "likely_active": "",
    "probably_fine": "",
    "questionable": " · ghost checklist: questionable",
    "likely_stale": " · ghost checklist: likely stale",
    "insufficient_data": " · too little data to judge staleness",
}


def subject(candidates: list[AlertCandidate], *, today: date | None = None) -> str:
    """Leads with whatever the digest leads with.

    Deliberately not `max(score)`. Candidates arrive in the same order Discover
    ranks them, which puts title-only matches below fully-compared ones however
    high their headline number -- so the maximum is routinely a thin-evidence
    100 sitting near the bottom. A subject line promising 100% above a body
    that opens at 48% is the kind of small lie that stops alerts being read.
    """
    if not candidates:
        return "Lighthouse: nothing new worth flagging"
    top = candidates[0]
    if len(candidates) == 1:
        return f"Lighthouse: {top.title} at {top.company_name} ({top.match_score}% match)"
    return f"Lighthouse: {len(candidates)} new postings, best {top.match_score}% match"


def render(candidates: list[AlertCandidate], *, today: date | None = None) -> str:
    """One message for the whole run."""
    if not candidates:
        return (
            "Nothing new cleared the bar this run.\n\n"
            "That is a real answer, not a failure: the postings are still in "
            "Discover, and this message only fires for ones worth interrupting "
            "you for.\n"
        )

    lines = [
        f"{len(candidates)} new posting{'s' if len(candidates) != 1 else ''} worth a look.",
        "",
    ]
    for c in candidates:
        head = f"  {c.match_score:>3}%  {c.title} — {c.company_name}"
        lines.append(head)

        facts = [c.evidence_note]
        if c.term_label:
            facts.append(c.term_label)
        if c.location:
            facts.append(c.location)
        lines.append(f"        {' · '.join(facts)}{GHOST_NOTE.get(c.ghost_label, '')}")

        if c.top_gaps:
            lines.append(f"        wants, and your corpus does not show: {', '.join(c.top_gaps)}")
        lines.append(f"        {c.url}")
        lines.append("")

    lines.append(
        "Scores are computed against your corpus. A score from a title alone is "
        "weak evidence and is marked as such above."
    )
    return "\n".join(lines)
