"""Turning a pasted block of names into contacts.

The workflow this supports is the one the compliance boundary leaves open: the
operator opens LinkedIn's own Alumni tool on their school's page, filters by
where people work, selects the results and pastes them here. LinkedIn built that
tool for exactly this purpose. Nothing is fetched, nothing is scraped, and the
operator's account is never touched by Lighthouse.

The parser is tolerant in the same way the markdown-table parser is, and for the
same reason: this is human-pasted text with no contract behind it. It returns
*drafts* the operator reviews before anything is written, which is the same
extract-then-commit split the corpus uses -- the zero-fabrication rule expressed
as an interface rather than a convention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contacts import ContactInput, Relationship

# "Software Engineer at Stripe", "SWE @ Stripe", "Software Engineer | Stripe".
_ROLE_AT_COMPANY = re.compile(r"^(?P<role>.{2,90}?)\s+(?:at|@|\||·|—|-)\s+(?P<company>.{2,80})$")

# Lines LinkedIn's UI puts in a copied block that are not part of a person.
_NOISE = re.compile(
    r"^(?:\d+(?:st|nd|rd|th)\s*(?:degree)?|connect|message|follow|view profile|"
    r"shared connections?|mutual connections?|·|see more|·\s*\d+.*)$",
    re.I,
)

# A location line, which we deliberately do not keep: it is about where they
# live, and the thing that matters is where they work.
_LOCATION = re.compile(
    r"(area|greater|metropolitan|,\s*[A-Z]{2}$|United States|Canada|Kingdom|Region)", re.I
)


@dataclass(slots=True)
class ParsedContact:
    """A candidate contact. No id, because nothing has been saved."""

    name: str
    role_title: str | None = None
    company_name: str | None = None
    line_count: int = 1

    def to_input(self, *, school: str | None = None) -> ContactInput:
        return ContactInput(
            name=self.name,
            role_title=self.role_title,
            company_name=self.company_name,
            school=school,
            # Someone found through an alumni search is an alumnus. It is the
            # single most useful thing to know about them, and re-deriving it
            # later from a school string the operator may never fill in would
            # lose it.
            relationship_type=(
                Relationship.ALUMNI.value if school else Relationship.COLD.value
            ),
        )


def _is_person_name(line: str) -> bool:
    """A name, rather than a role line, a location, or a stray fragment.

    Two to four capitalised words with no digits. Deliberately conservative: a
    role line wrongly read as a name creates a contact called "Senior Software
    Engineer", which the operator has to find and delete.

    Locations are excluded explicitly, because they pass every other test here
    -- "San Francisco Bay Area" and "New York, NY" are capitalised, digit-free
    and the right length, and a paste from LinkedIn puts one under every single
    person.
    """
    if any(ch.isdigit() for ch in line):
        return False
    if _LOCATION.search(line):
        return False
    words = line.split()
    if not 1 < len(words) <= 4:
        return False
    return all(w[:1].isupper() for w in words if w[:1].isalpha())


def parse_pasted_contacts(text: str, *, limit: int = 200) -> list[ParsedContact]:
    """Read a pasted block into candidate contacts.

    Handles the two shapes that actually come out of a browser selection: one
    person per block separated by blank lines, and one person per run of
    consecutive lines. Anything it cannot make sense of is dropped rather than
    guessed at -- a half-parsed contact is worse than a missing one, because the
    operator will not notice it is wrong until they use the name.
    """
    if not text or not text.strip():
        return []

    lines = [
        line.strip()
        for line in text.replace("\t", "\n").splitlines()
        if line.strip() and not _NOISE.match(line.strip())
    ]

    parsed: list[ParsedContact] = []
    current: ParsedContact | None = None

    for line in lines:
        if _is_person_name(line) and not _ROLE_AT_COMPANY.match(line):
            if current is not None:
                parsed.append(current)
            current = ParsedContact(name=line)
            continue

        if current is None:
            continue

        match = _ROLE_AT_COMPANY.match(line)
        if match and not current.company_name:
            current.role_title = match.group("role").strip()
            current.company_name = match.group("company").strip()
            current.line_count += 1
            continue

        # A bare company or role line, when the "X at Y" form was not used.
        if not current.role_title and not _LOCATION.search(line):
            current.role_title = line
            current.line_count += 1

    if current is not None:
        parsed.append(current)

    # A block that produced only names and no roles is usually a mis-parse of
    # something that was not a contact list at all.
    return parsed[:limit]
