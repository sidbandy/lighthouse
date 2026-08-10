"""Outreach drafts, grounded in the corpus and in real postings.

Two specific details make a cold message get answered: one about *them* that
proves you looked, and one about *you* that is checkable. Everything else --
the enthusiasm, the adjectives about their "innovative culture" -- is what
recruiters filter out, and most templates are made entirely of it.

So both details are sourced rather than generated:

* The thing about them comes from a **real posting at their company** that
  Lighthouse has ingested. "You're hiring a compiler engineer in Austin" is
  checkable, and it is true because we read it off their own board.
* The thing about the operator comes from a **corpus fact**, and the fact ids
  travel with the draft so the trace renders.

If the corpus is empty the draft is refused rather than written round the gap.
A message asserting things about someone with nothing behind it is exactly the
artifact this project exists not to produce -- and the person sending it would
be the one who has to defend it on a call.

Nothing here sends anything.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import llm
from ..core.models import Contact, CorpusFact, OperatorProfile, Posting
from ..core.textanalysis import is_technical, profile

# The spec's limit, and it is a real one. Past this a cold message stops being
# read, and the discipline of cutting to it is most of what makes the message
# good.
MAX_WORDS = 120


@dataclass(slots=True)
class DraftContext:
    """Everything a draft is allowed to draw on. Assembled before any writing."""

    contact: Contact
    facts: list[llm.SourceFact] = field(default_factory=list)
    # A real, checkable thing about their company, lifted from its own postings.
    company_hook: str | None = None
    hook_evidence: str | None = None
    operator_name: str | None = None
    operator_school: str | None = None
    shares_school: bool = False

    @property
    def company(self) -> str:
        return self.contact.company_name or "their team"


@dataclass(slots=True)
class Draft:
    """One message, with its provenance and its grounding verdict."""

    variant: str
    subject: str
    body: str
    source_fact_ids: list[uuid.UUID]
    provider: str
    is_fallback: bool
    grounding_note: str
    warnings: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.body.split())


class CannotDraft(ValueError):
    """Raised when there is not enough real material to write from."""


def _pick_facts(session: Session, contact: Contact, *, limit: int = 3) -> list[llm.SourceFact]:
    """The corpus facts most worth mentioning to this contact.

    Ranked by overlap with the language their company's own postings use, so a
    message to a systems team leads with the systems project rather than
    whichever fact happens to be first. Falls back to recency when there is
    nothing to compare against.
    """
    from ..core.config import get_settings

    uid = get_settings().operator_id
    facts = list(
        session.scalars(
            select(CorpusFact).where(CorpusFact.user_id == uid).order_by(CorpusFact.created_at)
        )
    )
    if not facts:
        return []

    company_terms: set[str] = set()
    if contact.company_id:
        descriptions = session.scalars(
            select(Posting.description)
            .where(
                Posting.company_id == contact.company_id,
                Posting.description_available.is_(True),
            )
            .limit(20)
        )
        for text in descriptions:
            if text:
                company_terms |= {t for t in profile(text).terms if is_technical(t)}

    def relevance(fact: CorpusFact) -> int:
        if not company_terms:
            return 0
        terms = {t for t in profile(f"{fact.title}\n{fact.body}").terms if is_technical(t)}
        return len(terms & company_terms)

    ranked = sorted(facts, key=lambda f: (-relevance(f), f.created_at))
    return [
        llm.SourceFact(fact_id=f.id, title=f.title, body=f.body or "") for f in ranked[:limit]
    ]


def _company_hook(session: Session, contact: Contact) -> tuple[str | None, str | None]:
    """One checkable thing about their company, from its own postings.

    This is the honest stand-in until Company Intelligence lands with careers
    pages and engineering blogs. It is narrower than a specificity hook but it
    has the property that matters: the operator can verify it in one click,
    because it came off the company's own board.
    """
    if not contact.company_id:
        return None, None
    posting = session.scalar(
        select(Posting)
        .where(
            Posting.company_id == contact.company_id,
            Posting.is_active.is_(True),
        )
        .order_by(Posting.posted_at.desc().nullslast())
        .limit(1)
    )
    if posting is None:
        return None, None
    where = posting.location_labels[0] if posting.location_labels else None
    hook = f"the {posting.title} opening" + (f" in {where}" if where else "")
    return hook, posting.url


def build_context(
    session: Session, contact: Contact, *, user_id: uuid.UUID | None = None
) -> DraftContext:
    from ..core.config import get_settings

    uid = user_id or get_settings().operator_id
    profile_row = session.scalar(select(OperatorProfile).where(OperatorProfile.user_id == uid))
    hook, evidence = _company_hook(session, contact)
    school = getattr(profile_row, "school", None)
    shares = bool(
        school and contact.school and school.strip().lower() == contact.school.strip().lower()
    )
    return DraftContext(
        contact=contact,
        facts=_pick_facts(session, contact),
        company_hook=hook,
        hook_evidence=evidence,
        operator_school=school,
        shares_school=shares,
    )


# --------------------------------------------------------------------------
# The deterministic writer
# --------------------------------------------------------------------------


def _opening(context: DraftContext, kind: str) -> str:
    name = context.contact.name.split()[0]
    if context.shares_school:
        return (
            f"Hi {name} — I'm a {context.operator_school} student "
            f"and saw you're at {context.company}."
        )
    if kind == "cold_outreach":
        return f"Hi {name} — I came across your work at {context.company}."
    return f"Hi {name},"


def _one_clause(body: str, *, max_chars: int = 150) -> str:
    """The first real clause of a fact, fit to drop into a sentence.

    Corpus bodies are usually résumé bullets separated by newlines with no
    sentence punctuation until the very end, so splitting on "." alone hands
    back the whole entry -- three bullets in the middle of a cold email, which
    is the difference between a message that gets read and one that does not.
    Line first, then sentence, then a hard length cap.
    """
    first_line = next((line.strip() for line in (body or "").splitlines() if line.strip()), "")
    clause = first_line.split(". ")[0].strip().rstrip(".;,")
    if len(clause) > max_chars:
        clause = clause[:max_chars].rsplit(" ", 1)[0] + "…"
    return clause


def _rule_based_body(context: DraftContext, kind: str, variant: str) -> str:
    """The template. Not a placeholder: with no key configured this is what
    ships, so it has to be a message a person would actually send."""
    fact = context.facts[0] if context.facts else None
    claim = fact.title if fact else ""
    detail = _one_clause(fact.body) if fact else ""
    about_me = f"{claim} — {detail}." if detail else f"{claim}."

    if kind == "thank_you":
        return (
            f"{_opening(context, kind)}\n\n"
            f"Thanks for taking the time to talk. The part about your team's work stuck with me, "
            f"and it lines up with what I've been building: {about_me}\n\n"
            f"I'll keep you posted on how the search goes. Thanks again."
        )

    if kind == "follow_up":
        return (
            f"{_opening(context, kind)}\n\n"
            f"Following up on my note from a couple of weeks ago — no worries if it's a busy "
            f"stretch. Still very interested in {context.company}. For context: {about_me}\n\n"
            f"Happy to keep it to fifteen minutes if you have any time."
        )

    if kind == "update":
        return (
            f"{_opening(context, kind)}\n\n"
            f"Wanted to send a quick update since we spoke: {about_me}\n\n"
            f"Hope things are going well on your side."
        )

    if kind == "reply":
        return (
            f"{_opening(context, kind)}\n\n"
            f"Thanks for getting back to me. To answer your question — {about_me}\n\n"
            f"Let me know what works and I'll fit around your schedule."
        )

    # Cold outreach, the default. Two registers, so the operator has a choice
    # without either being padding.
    hook = f" I saw {context.company_hook}." if context.company_hook else ""
    if variant == "direct":
        return (
            f"{_opening(context, kind)}{hook}\n\n"
            f"I'm a student looking at roles there for next cycle. Most recently: {about_me}\n\n"
            f"Would you be open to fifteen minutes to talk about what the team actually works on? "
            f"Happy to work around your schedule."
        )
    return (
        f"{_opening(context, kind)}{hook}\n\n"
        f"I've been working on something adjacent — {about_me} I'd like to understand how your "
        f"team approaches it before I apply.\n\n"
        f"Any chance of a short call in the next couple of weeks?"
    )


_VARIANTS = ("direct", "curious")

_SYSTEM = f"""You draft short outreach messages for a student's job search.

Hard rules:
- Under {MAX_WORDS} words. Shorter is better.
- Reference exactly one specific, verifiable detail about the recipient's company,
  taken only from the context given. Never invent one.
- Reference exactly one specific fact about the sender, taken only from the facts
  given. Never invent, embellish or round a number.
- No superlatives about the company. No "world-class", "amazing", "innovative".
- End with a low-friction ask: a short call. Never ask for a referral first contact.
- Plain sentences. No bullet points, no subject line in the body.
"""


def _prompt(context: DraftContext, kind: str, variant: str) -> str:
    facts = "\n".join(f"- {f.title}: {f.body}" for f in context.facts) or "- (none)"
    role = f", {context.contact.role_title}" if context.contact.role_title else ""
    alumni = f"Both attended {context.operator_school}.\n" if context.shares_school else ""
    return (
        f"Message type: {kind} ({variant} register).\n"
        f"Recipient: {context.contact.name}{role} at {context.company}.\n"
        f"Verifiable detail about their company: {context.company_hook or '(none available)'}\n"
        f"{alumni}"
        f"Facts about the sender, use exactly one:\n{facts}\n"
    )


def _subject(context: DraftContext, kind: str) -> str:
    if kind == "thank_you":
        return "Thank you"
    if kind == "update":
        return "Quick update"
    if kind == "follow_up":
        return f"Following up — {context.company}"
    if context.shares_school:
        return f"{context.operator_school} student — quick question about {context.company}"
    return f"Quick question about {context.company}"


def draft_messages(
    session: Session,
    contact: Contact,
    *,
    kind: str = "cold_outreach",
    provider: llm.LlmProvider | None = None,
    user_id: uuid.UUID | None = None,
) -> list[Draft]:
    """Two drafts for one contact. The operator picks one and edits it.

    Raises :class:`CannotDraft` when the corpus is empty. There is no useful
    version of "write about me using nothing about me", and producing a
    plausible-sounding message anyway is how someone ends up defending a claim
    they never made.
    """
    context = build_context(session, contact, user_id=user_id)
    if not context.facts:
        raise CannotDraft(
            "Nothing in your corpus to write from. A cold message works because it "
            "says something real and checkable about you — add a project or an "
            "experience on My corpus first."
        )

    drafts: list[Draft] = []
    seen_bodies: set[str] = set()
    for variant in _VARIANTS:
        fallback = _rule_based_body(context, kind, variant)
        conversation = llm.Conversation(
            system=_SYSTEM,
            notes={"fallback": fallback},
        ).user(_prompt(context, kind, variant))

        completion = llm.complete(
            conversation,
            sources=context.facts,
            require_grounding=True,
            provider=provider,
        )

        body = completion.text
        warnings: list[str] = []
        if not completion.grounding.is_clean:
            # Do not silently rewrite it. Hand back the deterministic draft,
            # which can only contain what the corpus says, and explain why.
            warnings.append(completion.grounding.describe())
            body = fallback
        words = len(body.split())
        if words > MAX_WORDS:
            warnings.append(
                f"{words} words — over the {MAX_WORDS}-word limit. Cut it before sending."
            )

        # Only the cold-outreach template has two genuinely different registers.
        # The others read the same whichever variant asked for them, and two
        # identical drafts is a worse offer than one -- it looks like a choice
        # and costs the reader the time to work out that it is not.
        if body in seen_bodies:
            continue
        seen_bodies.add(body)

        drafts.append(
            Draft(
                variant=variant,
                subject=_subject(context, kind),
                body=body,
                source_fact_ids=[f.fact_id for f in context.facts[:1]],
                provider=completion.provider.value,
                is_fallback=completion.is_fallback,
                grounding_note=completion.grounding.describe(),
                warnings=warnings,
            )
        )
    return drafts
