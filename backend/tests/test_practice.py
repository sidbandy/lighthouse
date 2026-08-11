"""Practice: the deterministic half, and the check that stops feedback lying.

Layer 1 has to be arithmetic and nothing else. That is what lets it work with no
key and no network, and — more importantly — what makes a trend across six
sessions mean something. A metric that moves because a model was in a different
mood is not a trend, so these tests pin the numbers exactly.

Layer 3 is the one with teeth: figures said out loud that the corpus does not
contain. "I led a team of five" when the record says three is the mistake that
gets repeated under pressure, and a coach that lets it through is worse than no
coach at all.
"""

import uuid

import pytest

from lighthouse.core import llm
from lighthouse.practice import delivery, feedback

# Roughly 150 words, so pace lands in the good band at 60 seconds.
_STEADY = " ".join(["word"] * 150)


def _facts(*bodies: str) -> list[llm.SourceFact]:
    return [llm.SourceFact(fact_id=uuid.uuid4(), title="Fact", body=b) for b in bodies]


class TestMeasurability:
    def test_too_short_to_measure_says_so(self):
        """Reporting 220 wpm off four words is arithmetic pretending to be
        insight."""
        report = delivery.analyse("um yeah sure", duration_sec=3)
        assert not report.is_measurable
        assert report.metrics == []
        assert "Too short" in report.summary()

    def test_a_real_answer_is_measurable(self):
        assert delivery.analyse(_STEADY, duration_sec=60).is_measurable


class TestPace:
    def test_the_conversational_band_reads_as_good(self):
        report = delivery.analyse(_STEADY, duration_sec=60)
        assert report.by_key("wpm").verdict == "good"

    def test_rushing_is_called_out(self):
        """The most common tell in a first mock, and the easiest to fix once
        it is named."""
        report = delivery.analyse(" ".join(["word"] * 200), duration_sec=60)
        metric = report.by_key("wpm")
        assert metric.verdict == "off"
        assert "Rushing" in metric.detail

    def test_slow_is_a_watch_not_a_failure(self):
        report = delivery.analyse(" ".join(["word"] * 80), duration_sec=60)
        assert report.by_key("wpm").verdict == "watch"


class TestFillers:
    def test_multi_word_fillers_are_counted_once(self):
        """"you know" must not also register as two separate words."""
        count, _ = delivery.count_fillers("so you know I mean it was kind of hard")
        assert count == 3

    def test_filler_words_inside_other_words_are_not_counted(self):
        """"unlike" contains "like"; "likely" does too."""
        count, _ = delivery.count_fillers("that is unlikely and unlike the other one")
        assert count == 0

    def test_examples_lead_with_the_most_frequent(self):
        """"um ×7" is the one worth knowing about; matching order would bury it."""
        _, examples = delivery.count_fillers("um um um basically uh")
        assert examples[0].startswith("um")

    def test_a_clean_answer_reads_as_clean(self):
        report = delivery.analyse(_STEADY, duration_sec=60)
        assert report.by_key("filler_density").verdict == "good"

    def test_heavy_filler_use_is_flagged(self):
        text = " ".join(["um like you know word word word"] * 12)
        report = delivery.analyse(text, duration_sec=60)
        assert report.by_key("filler_density").verdict == "off"


class TestLengthAndSilence:
    def test_a_ninety_second_answer_is_the_sweet_spot(self):
        report = delivery.analyse(" ".join(["word"] * 210), duration_sec=90)
        assert report.by_key("duration").verdict == "good"

    def test_rambling_is_flagged(self):
        report = delivery.analyse(" ".join(["word"] * 500), duration_sec=240)
        assert report.by_key("duration").verdict == "off"

    def test_a_short_answer_suggests_the_missing_result(self):
        report = delivery.analyse(" ".join(["word"] * 60), duration_sec=25)
        assert "Result is missing" in report.by_key("duration").detail

    def test_silences_are_absent_rather_than_guessed_without_timings(self):
        """A guessed pause is worse than no pause."""
        report = delivery.analyse(_STEADY, duration_sec=60)
        assert report.by_key("silences") is None

    def test_long_stalls_are_counted_when_timings_exist(self):
        words = [
            delivery.Word("a", 0, 1),
            delivery.Word("b", 8, 9),
            delivery.Word("c", 17, 18),
            delivery.Word("d", 26, 27),
        ]
        report = delivery.analyse(_STEADY, duration_sec=60, words=words)
        metric = report.by_key("silences")
        assert metric.value == 3
        assert metric.verdict == "off"

    def test_longest_silence_is_the_real_gap(self):
        words = [delivery.Word("a", 0, 1), delivery.Word("b", 7.5, 8)]
        assert delivery.longest_silence(words) == pytest.approx(6.5)


class TestTrend:
    def test_two_sessions_are_not_a_trend(self):
        assert delivery.trend("wpm", "Pace", [180.0, 150.0]).statement().endswith(
            "not a trend yet."
        )

    def test_a_real_improvement_is_reported_as_a_direction(self):
        result = delivery.trend("filler", "Fillers", [10.0, 8.0, 6.0, 5.0])
        assert "down" in result.statement()
        assert "4 sessions" in result.statement()

    def test_one_session_yields_nothing(self):
        assert delivery.trend("wpm", "Pace", [150.0]) is None


class TestStructure:
    def test_a_full_star_answer_is_recognised(self):
        transcript = (
            "We were behind on the ingest pipeline. I had to get it working before the demo. "
            "So I rewrote the persistence layer. As a result we cut the run time."
        )
        findings = feedback.check_structure(transcript)
        assert all(f.present for f in findings)

    def test_a_missing_result_is_the_one_that_gets_flagged(self):
        transcript = (
            "We were behind on the pipeline. I had to fix it. So I rewrote the parser."
        )
        findings = {f.part: f for f in feedback.check_structure(transcript)}
        assert not findings["result"].present
        assert "what changed" in findings["result"].advice

    def test_advice_names_something_concrete(self):
        for finding in feedback.check_structure(""):
            assert len(finding.advice) > 20


class TestDrift:
    def test_a_figure_the_corpus_backs_is_not_flagged(self):
        sources = _facts("Handled 50000 requests per second.")
        assert feedback.check_drift("It handled 50000 requests a second.", sources) == []

    def test_a_figure_that_grew_in_the_telling_is_caught(self):
        """The canonical failure this layer exists for."""
        sources = _facts("Worked with a team of 3.")
        drift = feedback.check_drift("I led a team of 9 on it.", sources)
        assert [d.claim for d in drift] == ["9"]

    def test_an_empty_corpus_flags_nothing(self):
        """There is no drift from a record that does not exist, and flagging
        every number would make the whole panel noise."""
        assert feedback.check_drift("We shipped to 9000 users.", []) == []


class TestFeedbackAssembly:
    def test_it_works_with_no_model_at_all(self):
        result = feedback.build("I had to fix it. So I rewrote the parser.")
        assert result.provider == llm.Provider.RULE_BASED.value
        assert result.notes.strip()

    def test_drift_leads_the_advice_when_present(self):
        sources = _facts("A team of 3.")
        result = feedback.build(
            "As a result I led a team of 12 and we shipped it.", sources=sources
        )
        assert "settle the figures" in result.notes

    def test_a_model_that_invents_a_figure_is_discarded(self):
        """Feedback that invents is the one failure this module cannot ship, so
        the deterministic note is used instead of the model's."""

        class Fabricator:
            name = llm.Provider.GEMINI

            def complete(self, conversation):
                return "Great work scaling that to 40000 users."

        sources = _facts("A small internal tool.")
        result = feedback.build(
            "I had to fix it. So I rewrote it. As a result it worked.",
            sources=sources,
            provider=Fabricator(),
        )
        assert "40000" not in result.notes

    def test_the_summary_names_what_is_missing(self):
        result = feedback.build("So I rewrote the parser.")
        assert "Missing:" in result.summary()
