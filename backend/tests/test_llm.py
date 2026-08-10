"""The provider layer, and the contract that stops it inventing things.

The grounding check is deliberately narrow: numbers, and only ones a reader
would plausibly verify. A general "is this supported by the sources" test is
either hand-waving or another model call, whereas a concrete figure that appears
nowhere in the operator's own record is a specific, checkable defect — and it is
the one that gets repeated out loud in a real interview.

The fallback tests matter as much. With no key configured, which is the default,
the rule-based path *is* the product. A feature whose template is a placeholder
is a feature that does not work for most people who run this.
"""

import uuid

import pytest

from lighthouse.core import llm


def _facts(*bodies: str) -> list[llm.SourceFact]:
    return [llm.SourceFact(fact_id=uuid.uuid4(), title="Fact", body=b) for b in bodies]


class TestVerifyGrounding:
    def test_a_figure_from_the_corpus_passes(self):
        sources = _facts("Handled 50000 requests per second.")
        assert llm.verify_grounding("It handled 50000 requests per second.", sources).is_clean

    def test_a_figure_the_corpus_does_not_have_is_caught(self):
        """The canonical failure: the corpus says three, the answer says five."""
        sources = _facts("Worked with a team of 3 on the ledger service.")
        report = llm.verify_grounding("I led a team of 8.", sources)
        assert report.unsupported_numbers == ["8"]
        assert not report.is_clean

    def test_percentages_are_checked(self):
        sources = _facts("Cut latency 40% with a cache.")
        assert llm.verify_grounding("Cut latency 40%.", sources).is_clean
        assert not llm.verify_grounding("Cut latency 62%.", sources).is_clean

    def test_years_are_not_claims(self):
        """A message that mentions graduating in 2027 is not asserting a metric."""
        assert llm.verify_grounding("Graduating in 2027.", _facts("Anything.")).is_clean

    def test_small_counts_in_prose_are_ignored(self):
        """"two or three things" would otherwise flood the report and train the
        reader to skip it."""
        assert llm.verify_grounding("I have 3 projects and 2 internships.", _facts("x")).is_clean

    def test_commas_do_not_hide_a_match(self):
        sources = _facts("Processed 50000 rows.")
        assert llm.verify_grounding("Processed 50,000 rows.", sources).is_clean

    def test_the_description_names_the_offending_figure(self):
        report = llm.verify_grounding("Grew it 71%.", _facts("No numbers here."))
        assert "71" in report.describe()

    def test_no_sources_means_every_figure_is_unsupported(self):
        report = llm.verify_grounding("Shipped to 9000 users.", [])
        assert report.unsupported_numbers == ["9000"]


class TestFallback:
    def test_the_rule_based_provider_uses_the_callers_template(self):
        conversation = llm.Conversation(notes={"fallback": "deterministic"})
        assert llm.RuleBasedProvider().complete(conversation) == "deterministic"

    def test_a_callable_template_is_allowed(self):
        conversation = llm.Conversation(notes={"fallback": lambda c: "computed"})
        assert llm.RuleBasedProvider().complete(conversation) == "computed"

    def test_a_caller_with_no_template_is_a_caller_that_is_not_finished(self):
        with pytest.raises(NotImplementedError):
            llm.RuleBasedProvider().complete(llm.Conversation())

    def test_a_failing_provider_degrades_rather_than_raising(self):
        """Quota, network and a malformed response are the same event from the
        caller's side, and the answer to all of them is the template."""

        class Broken:
            name = llm.Provider.GEMINI

            def complete(self, conversation):
                raise RuntimeError("429 rate limited")

        result = llm.complete(
            llm.Conversation(notes={"fallback": "template"}),
            sources=_facts("x"),
            provider=Broken(),
        )
        assert result.text == "template"
        assert result.is_fallback
        assert result.provider is llm.Provider.RULE_BASED


class TestGroundingContract:
    def test_grounded_output_carries_its_fact_ids(self):
        sources = _facts("Built a thing.")
        result = llm.complete(
            llm.Conversation(notes={"fallback": "Built a thing."}), sources=sources
        )
        assert result.source_fact_ids == [s.fact_id for s in sources]
        assert result.is_grounded

    def test_requiring_grounding_with_nothing_to_ground_in_raises(self):
        with pytest.raises(llm.NotGrounded):
            llm.complete(
                llm.Conversation(notes={"fallback": "x"}), sources=[], require_grounding=True
            )

    def test_output_with_an_unsupported_figure_is_not_grounded(self):
        result = llm.complete(
            llm.Conversation(notes={"fallback": "I shipped to 9000 users."}),
            sources=_facts("No figures."),
        )
        assert not result.is_grounded
        assert result.grounding.unsupported_numbers == ["9000"]


class TestConversation:
    def test_it_keeps_its_own_state(self):
        """Sized for a live mock from the start: retrofitting multi-turn later
        would mean rewriting every caller."""
        conversation = llm.Conversation(system="you are an interviewer")
        conversation.user("first").assistant("probe").user("second")
        assert len(conversation.messages) == 3
        assert conversation.last_user_message == "second"

    def test_notes_carry_structured_state_across_turns(self):
        conversation = llm.Conversation(notes={"question": "tell me about a conflict"})
        conversation.user("...")
        assert conversation.notes["question"] == "tell me about a conflict"
