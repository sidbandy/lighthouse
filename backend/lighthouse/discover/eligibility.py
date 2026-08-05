"""Checks a posting's stated graduation window against the operator's.

Applying outside a stated class-year window is the commonest wasted application
a student makes. Reports eligible, not eligible, or not stated -- the last of
which is the usual answer and is never reported as either of the others.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ..core.models import EmploymentType

# "graduating in 2027", "class of 2028", "expected graduation: May 2027",
# "December 2026 graduates". Captures every 4-digit year in the vicinity so a
# range ("2027 or 2028") is caught whole.
_GRAD_CONTEXT = re.compile(
    r"[^.\n]{0,80}\b(?:graduat\w*|class of|degree completion|commencement)\b[^.\n]{0,80}",
    re.I,
)
_YEAR = re.compile(r"\b(20[2-4]\d)\b")

# Postings that require you to still be enrolled afterwards. A senior graduating
# before the internship ends is not eligible for these, and it is one of the
# few genuinely unambiguous knockouts in a job description.
_MUST_RETURN = re.compile(
    r"\b(return(?:ing)? to (?:school|university|campus|studies|your degree)|"
    r"currently enrolled|must be enrolled|enrolled (?:in|at) an? (?:accredited )?"
    r"(?:university|college|degree)|pursuing a (?:bachelor|master|degree))\b",
    re.I,
)


class Verdict(StrEnum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    NOT_STATED = "not_stated"


@dataclass(slots=True)
class EligibilityCheck:
    """One checkable claim about whether the operator can apply."""

    verdict: Verdict
    headline: str
    detail: str
    evidence: str | None = None

    @property
    def is_blocking(self) -> bool:
        return self.verdict is Verdict.NOT_ELIGIBLE


def _stated_years(description: str) -> tuple[set[int], str | None]:
    """Graduation years the posting names, and the sentence naming them."""
    years: set[int] = set()
    evidence: str | None = None
    for window in _GRAD_CONTEXT.finditer(description):
        found = {int(y) for y in _YEAR.findall(window.group(0))}
        if found:
            years |= found
            if evidence is None:
                evidence = " ".join(window.group(0).split())
    return years, evidence


def check_graduation(
    description: str | None,
    *,
    graduation_year: int | None,
    employment_type: EmploymentType | str | None = None,
) -> EligibilityCheck:
    """Compare the posting's stated graduation window against the operator's.

    Returns ``NOT_STATED`` whenever either side is silent. Guessing an
    eligibility window the posting never gave — or one the operator never told
    us — would be exactly the kind of invented claim this project refuses to
    make, and here it would cost a real application.
    """
    if not description:
        return EligibilityCheck(
            Verdict.NOT_STATED,
            "No description to check",
            "This posting was listed without its text, so its graduation window is unknown.",
        )
    if graduation_year is None:
        return EligibilityCheck(
            Verdict.NOT_STATED,
            "Set your graduation term",
            "Add when you graduate to your profile and Lighthouse can check this "
            "against every posting automatically.",
        )

    years, evidence = _stated_years(description)

    if years:
        if graduation_year in years:
            return EligibilityCheck(
                Verdict.ELIGIBLE,
                f"Wants {_join(years)} grads — that's you",
                f"You graduate in {graduation_year}, which this posting names.",
                evidence,
            )
        return EligibilityCheck(
            Verdict.NOT_ELIGIBLE,
            f"Wants {_join(years)} grads — you graduate {graduation_year}",
            "Worth checking the posting before you skip it; recruiters do make "
            "exceptions, and this is read out of prose.",
            evidence,
        )

    # No year given. The "must still be enrolled" rule is the other common
    # window, and it only knocks anyone out for internships.
    must_return = _MUST_RETURN.search(description)
    is_internship = str(getattr(employment_type, "value", employment_type) or "") == "internship"
    if must_return and is_internship:
        return EligibilityCheck(
            Verdict.NOT_STATED,
            "Requires you to still be enrolled",
            "This asks for candidates continuing their degree afterwards. Check that "
            "against your graduation term.",
            " ".join(must_return.group(0).split()),
        )

    return EligibilityCheck(
        Verdict.NOT_STATED,
        "No graduation window stated",
        "This posting does not say which class years it wants, so nothing here rules you out.",
    )


def _join(years: set[int]) -> str:
    ordered = sorted(years)
    if len(ordered) == 1:
        return str(ordered[0])
    return ", ".join(str(y) for y in ordered[:-1]) + f" or {ordered[-1]}"
