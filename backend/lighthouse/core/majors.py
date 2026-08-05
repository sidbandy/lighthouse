"""Majors, and what they imply about the roles worth showing someone.

Lighthouse is for students, so "what do you study" is the question it can
actually ask — and it is a far better opening filter than asking a sophomore to
pick role families out of a taxonomy they have never seen. A finance major
should not have to know that Lighthouse calls their world ``finance`` and
``business``; they should type "Finance" and get the right list.

The mapping is deliberately generous. A CS major gets swe, ai_ml, data *and*
quant, because plenty of CS students end up in all four and hiding a lane is
worse than showing one the operator can uncheck. It is a starting point that
seeds the filter, never a cage: ``target_role_families`` is editable
immediately afterwards, and this module is only consulted when it is empty.

Matching is on keywords rather than exact names because majors are written a
hundred ways ("CS", "Computer Science & Engineering", "B.S. Computer Science").
"""

from __future__ import annotations

import re

from .models import RoleFamily

# Keyword -> role families. Ordered most-specific first: "computer engineering"
# has to be tested before "engineering", or every engineer becomes a mechanical
# engineer. Within a match, families are listed best-fit first.
_MAJOR_RULES: tuple[tuple[tuple[str, ...], tuple[RoleFamily, ...]], ...] = (
    (
        ("computer science", "computer engineering", "software", "informatics", "comp sci", "cs"),
        (RoleFamily.SWE, RoleFamily.AI_ML, RoleFamily.DATA, RoleFamily.SECURITY),
    ),
    (
        ("data science", "data analytics", "statistics", "biostatistics", "applied math"),
        (RoleFamily.DATA, RoleFamily.AI_ML, RoleFamily.QUANT, RoleFamily.SCIENCE),
    ),
    (
        ("artificial intelligence", "machine learning", "cognitive science"),
        (RoleFamily.AI_ML, RoleFamily.DATA, RoleFamily.SWE),
    ),
    (
        ("mathematics", "math", "physics", "econometrics"),
        (RoleFamily.QUANT, RoleFamily.DATA, RoleFamily.SCIENCE, RoleFamily.AI_ML),
    ),
    (
        ("electrical", "computer eng", "robotics", "mechatronics"),
        (RoleFamily.HARDWARE, RoleFamily.SWE, RoleFamily.MECHANICAL),
    ),
    (
        ("mechanical", "aerospace", "civil", "materials", "manufacturing", "industrial eng"),
        (RoleFamily.MECHANICAL, RoleFamily.HARDWARE, RoleFamily.SCIENCE),
    ),
    (
        ("chemical eng", "biomedical", "bioengineering"),
        (RoleFamily.SCIENCE, RoleFamily.MECHANICAL, RoleFamily.DATA),
    ),
    (
        ("finance", "accounting", "actuarial"),
        (RoleFamily.FINANCE, RoleFamily.BUSINESS, RoleFamily.QUANT, RoleFamily.DATA),
    ),
    (
        ("economics", "econ"),
        (RoleFamily.FINANCE, RoleFamily.CONSULTING, RoleFamily.BUSINESS, RoleFamily.DATA),
    ),
    (
        ("business", "management", "supply chain", "operations", "entrepreneur"),
        (RoleFamily.BUSINESS, RoleFamily.CONSULTING, RoleFamily.FINANCE, RoleFamily.PRODUCT),
    ),
    (
        ("marketing", "advertising", "communications", "public relations", "journalism"),
        (RoleFamily.MARKETING, RoleFamily.BUSINESS, RoleFamily.DESIGN),
    ),
    (
        ("design", "hci", "human-computer", "user experience", "graphic", "industrial design"),
        (RoleFamily.DESIGN, RoleFamily.PRODUCT, RoleFamily.MARKETING),
    ),
    (
        ("biology", "chemistry", "neuroscience", "environmental", "geology", "psychology"),
        (RoleFamily.SCIENCE, RoleFamily.DATA, RoleFamily.BUSINESS),
    ),
    (
        ("information systems", "mis", "information technology"),
        (RoleFamily.SWE, RoleFamily.DATA, RoleFamily.BUSINESS, RoleFamily.SECURITY),
    ),
    (
        ("cybersecurity", "information security"),
        (RoleFamily.SECURITY, RoleFamily.SWE, RoleFamily.DATA),
    ),
    (
        ("political science", "international", "public policy", "history", "english", "philosophy"),
        (RoleFamily.CONSULTING, RoleFamily.BUSINESS, RoleFamily.MARKETING),
    ),
)

# A shortlist for the picker. Free text is still accepted -- this is what the UI
# offers, not what it allows.
COMMON_MAJORS: tuple[str, ...] = (
    "Computer Science",
    "Data Science",
    "Electrical Engineering",
    "Mechanical Engineering",
    "Computer Engineering",
    "Mathematics",
    "Statistics",
    "Physics",
    "Finance",
    "Economics",
    "Accounting",
    "Business Administration",
    "Marketing",
    "Information Systems",
    "Cybersecurity",
    "Industrial Engineering",
    "Chemical Engineering",
    "Biomedical Engineering",
    "Biology",
    "Chemistry",
    "Psychology",
    "Graphic Design",
    "Human-Computer Interaction",
    "Political Science",
    "Communications",
)

DEGREE_LEVELS: tuple[tuple[str, str], ...] = (
    ("associate", "Associate"),
    ("bachelors", "Bachelor's"),
    ("masters", "Master's"),
    ("phd", "PhD"),
)


def role_families_for(major: str | None) -> list[str]:
    """Role families worth showing someone with this major, best fit first.

    Returns an empty list for an unrecognised major rather than guessing —
    showing everything is a better default than showing the wrong thing
    confidently, and the UI can say "we don't know your field yet, here's
    everything" honestly.
    """
    if not major or not major.strip():
        return []

    text = major.lower()
    matched: list[str] = []
    for keywords, families in _MAJOR_RULES:
        if any(re.search(rf"\b{re.escape(k)}", text) for k in keywords):
            for family in families:
                if family.value not in matched:
                    matched.append(family.value)
    return matched
