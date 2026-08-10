"""The LLM provider layer, and the grounding contract every call passes through.

Three things this exists to guarantee, in order of how much they matter.

**Nothing here can invent a fact about the operator.** A caller declares the
corpus facts an answer is allowed to draw on, and the output is checked against
them before it is returned. The check is deterministic and narrow -- it looks for
numbers the sources do not contain -- because that is the failure that actually
sinks people: "led a team of five" when the corpus says three is the kind of
thing you repeat under pressure in a real interview. A wide, fuzzy check would
be reassuring and worthless.

**Every call has a rule-based fallback.** The app works with no key, no network
and no quota. A provider that is unconfigured, rate-limited or broken degrades to
a deterministic path rather than surfacing an error, because a networking tool
that stops working when a free tier runs out is a networking tool nobody trusts.

**The shape is multi-turn from the start.** A behavioural mock has to remember
what was said three minutes ago, so a :class:`Conversation` carries rolling
state rather than a single prompt string. Retrofitting that later would mean
rewriting every caller.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from .config import get_settings

logger = logging.getLogger(__name__)


class Provider(StrEnum):
    GEMINI = "gemini"
    RULE_BASED = "rule_based"


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(slots=True)
class Message:
    role: Role
    content: str


@dataclass(slots=True)
class SourceFact:
    """One corpus fact an answer is allowed to draw on.

    ``fact_id`` travels with the text so a generated artifact can render its
    provenance -- "built from: Ledger service, Cloudify internship" -- which is
    what turns the zero-fabrication rule from a promise into something the
    operator can check.
    """

    fact_id: uuid.UUID
    title: str
    body: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}".strip()


@dataclass(slots=True)
class Conversation:
    """A running exchange. Carries its own state so a session can continue.

    ``notes`` is free-form structured state for the caller -- the question under
    discussion, hints already given, whatever the mode needs. It is passed back
    on every turn rather than being re-derived from the transcript.
    """

    system: str = ""
    messages: list[Message] = field(default_factory=list)
    notes: dict = field(default_factory=dict)

    def say(self, role: Role, content: str) -> Conversation:
        self.messages.append(Message(role=role, content=content))
        return self

    def user(self, content: str) -> Conversation:
        return self.say(Role.USER, content)

    def assistant(self, content: str) -> Conversation:
        return self.say(Role.ASSISTANT, content)

    @property
    def last_user_message(self) -> str:
        return next(
            (m.content for m in reversed(self.messages) if m.role is Role.USER),
            "",
        )


@dataclass(slots=True)
class GroundingReport:
    """What the output claimed that the sources do not support."""

    unsupported_numbers: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.unsupported_numbers

    def describe(self) -> str:
        if self.is_clean:
            return "Every figure in this text appears in the facts it was built from."
        joined = ", ".join(self.unsupported_numbers)
        return (
            f"Not supported by your corpus: {joined}. "
            "Either the fact is out of date or the text overstated it."
        )


@dataclass(slots=True)
class Completion:
    """A generated answer, with its provenance and its grounding verdict."""

    text: str
    provider: Provider
    source_fact_ids: list[uuid.UUID] = field(default_factory=list)
    grounding: GroundingReport = field(default_factory=GroundingReport)
    # True when the configured provider could not be used and the deterministic
    # path produced this instead. Surfaced rather than hidden: a template and a
    # model are different things and the operator should know which they got.
    is_fallback: bool = False

    @property
    def is_grounded(self) -> bool:
        return bool(self.source_fact_ids) and self.grounding.is_clean


class NotGrounded(ValueError):
    """Raised when a caller asks for grounded output with nothing to ground it in.

    Deliberately an error rather than a silent empty result: a draft about the
    operator with no corpus behind it is exactly the artifact this project
    refuses to produce.
    """


# Figures a reader would never check, and that carry no claim about the
# operator. Years and small counts inside ordinary prose ("2 or 3 things") would
# otherwise flood the report and train the reader to ignore it.
_NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?%?\b")
_IGNORED_NUMBERS = frozenset({"1", "2", "3", "4", "5", "10", "15", "20", "30"})


def _numbers_in(text: str) -> list[str]:
    return [n.replace(",", "") for n in _NUMBER_RE.findall(text)]


def verify_grounding(text: str, sources: list[SourceFact]) -> GroundingReport:
    """Check the figures in ``text`` against the facts it was built from.

    Only numbers, and only ones a reader would plausibly check. Language models
    are fluent enough that a general "is this supported" test is either
    hand-waving or another model call; a concrete figure that appears nowhere in
    the operator's own record is a specific, checkable defect, and it is the one
    that gets repeated out loud in an interview.

    Years are exempt: a message that mentions the current year is not making a
    claim about the operator.
    """
    corpus_numbers = set()
    for source in sources:
        corpus_numbers.update(_numbers_in(source.text))

    unsupported = []
    for number in _numbers_in(text):
        bare = number.rstrip("%")
        if bare in _IGNORED_NUMBERS or number in corpus_numbers or bare in corpus_numbers:
            continue
        # A four-digit number in a plausible year range is calendar, not claim.
        if bare.isdigit() and 1900 <= int(bare) <= 2100:
            continue
        unsupported.append(number)
    return GroundingReport(unsupported_numbers=sorted(set(unsupported)))


class LlmProvider(Protocol):
    """Anything that can continue a conversation."""

    name: Provider

    def complete(self, conversation: Conversation) -> str: ...


class RuleBasedProvider:
    """The deterministic path.

    Not a stub. It is the provider whenever no key is configured, which is the
    default, so every caller has to supply a template good enough to ship. That
    constraint is deliberate: it keeps the rule-based output honest work rather
    than a placeholder nobody reads.

    The template lives with the caller -- put it in ``conversation.notes`` under
    ``fallback`` -- because only the caller knows what a good answer looks like
    for its own feature.
    """

    name = Provider.RULE_BASED

    def complete(self, conversation: Conversation) -> str:
        fallback = conversation.notes.get("fallback")
        if callable(fallback):
            return str(fallback(conversation))
        if isinstance(fallback, str) and fallback.strip():
            return fallback
        raise NotImplementedError(
            "The rule-based provider needs a 'fallback' in conversation.notes. "
            "Every feature has to work with no key and no network, so a caller "
            "without one is a caller that has not finished."
        )


class GeminiProvider:
    """Gemini's free tier, called over plain HTTP.

    No SDK: one POST to a documented endpoint is not worth a dependency, and the
    dependency would need pinning against a machine that cannot afford large
    installs.
    """

    name = Provider.GEMINI

    def __init__(self, api_key: str, model: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, conversation: Conversation) -> str:
        import httpx

        contents = [
            {
                "role": "model" if m.role is Role.ASSISTANT else "user",
                "parts": [{"text": m.content}],
            }
            for m in conversation.messages
            if m.role is not Role.SYSTEM
        ]
        payload: dict = {"contents": contents}
        if conversation.system:
            payload["systemInstruction"] = {"parts": [{"text": conversation.system}]}

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        response = httpx.post(
            url,
            json=payload,
            headers={"x-goog-api-key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            raise RuntimeError("Gemini returned an empty completion")
        return text


def build_provider() -> LlmProvider:
    """The configured provider, or the deterministic one when it is unusable."""
    settings = get_settings()
    if settings.llm_provider == Provider.GEMINI and settings.gemini_api_key:
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=settings.http_timeout_seconds,
        )
    return RuleBasedProvider()


def complete(
    conversation: Conversation,
    *,
    sources: list[SourceFact] | None = None,
    require_grounding: bool = False,
    provider: LlmProvider | None = None,
) -> Completion:
    """Continue ``conversation``, then check what came back.

    ``require_grounding`` is for anything that speaks about the operator in their
    own voice. With it set, an empty ``sources`` raises rather than returning an
    ungrounded draft -- there is no useful version of "write about me using
    nothing about me".

    A provider that raises for any reason falls through to the rule-based path.
    Quota, network, a malformed response: from the caller's side they are the
    same event, and the answer to all of them is the deterministic template.
    """
    sources = sources or []
    if require_grounding and not sources:
        raise NotGrounded(
            "This needs at least one corpus fact behind it. Add something real "
            "to your corpus first -- a draft with nothing behind it is the one "
            "thing Lighthouse will not write."
        )

    provider = provider or build_provider()
    is_fallback = False
    try:
        text = provider.complete(conversation)
    except NotImplementedError:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure has the same answer
        logger.warning("%s failed (%s); falling back to rule-based", provider.name, exc)
        text = RuleBasedProvider().complete(conversation)
        provider = RuleBasedProvider()
        is_fallback = True

    return Completion(
        text=text.strip(),
        provider=provider.name,
        source_fact_ids=[s.fact_id for s in sources],
        grounding=verify_grounding(text, sources),
        is_fallback=is_fallback,
    )
