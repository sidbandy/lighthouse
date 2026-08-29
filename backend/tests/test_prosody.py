"""The acoustic pass: finding the fillers a transcriber deleted.

The premise under test is unusual enough to state plainly. Every transcriber
this project can run drops "um" — browser speech recognition treats it as noise,
Whisper was trained on cleaned subtitles. So the fillers are missing from the
words by construction, and the detector works by looking for the hole they left:
time the voice detector called speech and the transcriber assigned no word to.

That makes the interesting tests the ones about *disagreement* between two
signals, and the ones that stop the detector claiming more than it measured —
a laugh is also voiced and untranscribed, and calling it a filled pause would be
the same invented number this project refuses everywhere else.

No audio is involved. Everything here is intervals, which is the point: the
analysis is separable from the machinery that produces them, so it is
deterministic and testable without a microphone.
"""

import pytest

from lighthouse.practice import prosody
from lighthouse.practice.delivery import Word
from lighthouse.practice.prosody import PauseKind, Span


def w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


class TestIntervalMath:
    def test_subtract_removes_a_hole_from_the_middle(self):
        left = prosody.subtract([Span(0, 10)], [Span(4, 6)])
        assert [(s.start, s.end) for s in left] == [(0, 4), (6, 10)]

    def test_subtract_handles_a_hole_that_spans_the_whole_interval(self):
        assert prosody.subtract([Span(2, 5)], [Span(0, 10)]) == []

    def test_merge_collapses_touching_intervals(self):
        merged = prosody.merge([Span(0, 2), Span(2, 4), Span(9, 10)])
        assert [(s.start, s.end) for s in merged] == [(0, 4), (9, 10)]

    def test_overlapping_words_do_not_double_subtract(self):
        """Transcriber word timings can overlap by a few milliseconds. Merging
        first is what stops that producing a negative-length residue."""
        left = prosody.subtract([Span(0, 5)], [Span(1, 3), Span(2.9, 4)])
        assert [(s.start, s.end) for s in left] == [(0, 1), (4, 5)]


class TestVoicedGaps:
    def test_finds_the_um_the_transcriber_deleted(self):
        """The core case. The speaker said "I ... um ... built it": the voice
        detector heard sound straight through, the transcriber wrote two words
        and skipped the middle. The gap between them is the filler."""
        speech = [Span(0.0, 3.0)]
        words = [w("I", 0.0, 0.3), w("built", 1.2, 1.6), w("it", 1.6, 3.0)]

        gaps = prosody.voiced_gaps(speech, words)
        assert len(gaps) == 1
        assert gaps[0].start == pytest.approx(0.3)
        assert gaps[0].end == pytest.approx(1.2)
        assert gaps[0].is_probable_filler

    def test_silence_between_words_is_not_a_voiced_gap(self):
        """A pause with no sound in it is a pause, not a filler. The voice
        detector is what tells them apart, and it is the only thing that can."""
        speech = [Span(0.0, 0.3), Span(1.2, 3.0)]
        words = [w("I", 0.0, 0.3), w("built", 1.2, 1.6), w("it", 1.6, 3.0)]
        assert prosody.voiced_gaps(speech, words) == []

    def test_alignment_slop_is_not_reported_as_a_filler(self):
        """Word timings are good to about a tenth of a second. A 60ms residue is
        the transcriber's error bar, and reporting it would invent fillers out
        of measurement noise."""
        speech = [Span(0.0, 2.0)]
        words = [w("I", 0.0, 0.94), w("built", 1.0, 2.0)]
        assert prosody.voiced_gaps(speech, words) == []

    def test_a_long_voiced_span_is_reported_but_not_called_a_filler(self):
        """Two seconds of voice with no word is a laugh, a throat clear, or a
        word that failed to transcribe. It is shown, because it is real, and it
        is not counted, because the detector does not know which it was."""
        speech = [Span(0.0, 5.0)]
        words = [w("right", 0.0, 0.4), w("anyway", 4.0, 5.0)]

        gaps = prosody.voiced_gaps(speech, words)
        assert len(gaps) == 1
        assert not gaps[0].is_probable_filler
        assert "longer than a filler" in gaps[0].statement()

    def test_gaps_are_ordered_longest_first(self):
        """Longest first, because the four-second hole is the one worth playing
        back and matching order would bury it under a 0.2s one."""
        speech = [Span(0.0, 10.0)]
        words = [w("a", 0.0, 0.2), w("b", 1.0, 1.2), w("c", 3.0, 3.2), w("d", 3.4, 10.0)]

        gaps = prosody.voiced_gaps(speech, words)
        assert [round(g.duration, 1) for g in gaps] == [1.8, 0.8, 0.2]

    def test_a_report_with_no_gaps_says_so_rather_than_saying_zero_fillers(self):
        report = prosody.analyse([w("hello", 0.0, 5.0)], [Span(0.0, 5.0)], total_sec=5.0)
        assert report.filler_count == 0
        assert "No voiced time went untranscribed" in report.filler_statement()


class TestPauseTaxonomy:
    def test_a_pause_after_punctuation_is_phrasing(self):
        pause = prosody.classify_pause(w("shipped.", 0.0, 0.5), w("Then", 1.5, 2.0))
        assert pause.kind is PauseKind.JUNCTURE
        assert "punctuated" in pause.rule

    def test_a_pause_after_a_dangling_function_word_is_searching(self):
        """The clearest word-searching signal in speech: the speaker committed
        to a phrase and has not found its head yet."""
        pause = prosody.classify_pause(w("the", 0.0, 0.2), w("pipeline", 1.4, 2.0))
        assert pause.kind is PauseKind.HESITATION
        assert "ends no phrase" in pause.rule

    def test_an_unmarked_pause_defaults_to_mid_clause_not_to_phrasing(self):
        """"No evidence of a boundary" is not "evidence of no boundary", and the
        honest default is the one that does not flatter."""
        pause = prosody.classify_pause(w("rewrote", 0.0, 0.4), w("everything", 1.4, 2.0))
        assert pause.kind is PauseKind.HESITATION
        assert "no clause boundary was marked" in pause.rule

    def test_ordinary_word_spacing_is_not_a_pause(self):
        words = [w("I", 0.0, 0.2), w("built", 0.28, 0.6), w("it", 0.66, 0.9)]
        assert prosody.pauses(words) == []

    def test_the_statement_separates_phrasing_from_searching(self):
        words = [
            w("shipped.", 0.0, 0.5),
            w("Then", 1.5, 1.8),
            w("the", 1.8, 2.0),
            w("thing", 3.2, 3.6),
        ]
        report = prosody.ProsodyReport(
            gaps=[], pauses=prosody.pauses(words), fluency=prosody.fluency(words, [], total_sec=4)
        )
        assert report.juncture_pauses == 1
        assert report.hesitation_pauses == 1
        assert "1 at a clause boundary" in report.pause_statement()
        assert "1 mid-clause" in report.pause_statement()

    def test_all_mid_clause_pauses_are_named_as_such(self):
        words = [w("the", 0.0, 0.2), w("thing", 1.5, 1.8), w("of", 1.8, 2.0), w("it", 3.5, 3.8)]
        report = prosody.analyse(words, [], total_sec=4.0)
        assert "none at a clause boundary" in report.pause_statement()


class TestFluency:
    def test_fast_in_bursts_is_distinguished_from_genuinely_fast(self):
        """The measurement this module exists to make possible. 60 words in 60
        seconds is 60 wpm — slow — but if only 20 seconds carried sound, the
        speaker was articulating at 180 and stopping constantly. Those need
        opposite advice, and speaking rate alone cannot tell them apart."""
        words = [w(str(i), i * 0.1, i * 0.1 + 0.05) for i in range(60)]
        report = prosody.fluency(words, [Span(0, 10), Span(30, 40)], total_sec=60.0)

        assert round(report.speaking_rate) == 60
        assert round(report.articulation_rate) == 180
        assert report.phonation_ratio == pytest.approx(1 / 3)
        assert "stopping often" in report.statement()

    def test_steady_delivery_is_reported_as_steady(self):
        words = [w(str(i), i * 0.4, i * 0.4 + 0.35) for i in range(40)]
        report = prosody.fluency(words, [Span(0, 15.5)], total_sec=16.0)
        assert "steady" in report.statement()

    def test_no_words_measures_nothing_rather_than_dividing_by_zero(self):
        report = prosody.fluency([], [], total_sec=0.0)
        assert report.speaking_rate == 0.0
        assert report.articulation_rate == 0.0
        assert report.statement() == "Nothing to measure."


class TestFullPass:
    def test_the_spans_survive_so_the_operator_can_play_them_back(self):
        """A count is a number to argue with; a timestamp is something to hear.
        The spans are the deliverable, not the total."""
        speech = [Span(0.0, 6.0)]
        words = [w("So", 0.0, 0.2), w("I", 0.9, 1.0), w("rebuilt", 1.0, 1.6), w("it", 5.6, 6.0)]

        report = prosody.analyse(words, speech, total_sec=6.0)

        # Both spans are kept; only the one in the filler band is counted. The
        # four-second hole is real and gets shown, but the detector does not
        # know whether it was a laugh, a cough or a missed word — so it does not
        # guess.
        assert [round(g.duration, 1) for g in report.gaps] == [4.0, 0.7]
        assert report.filler_count == 1
        assert not report.gaps[0].is_probable_filler
        assert report.gaps[1].is_probable_filler
        assert report.gaps[1].statement().startswith("0:00")
        assert "Counted from the sound" in report.filler_statement()

    def test_filler_rate_is_per_minute_of_the_whole_answer(self):
        speech = [Span(0.0, 120.0)]
        words = [w("a", 0.0, 0.2), w("b", 1.0, 60.0), w("c", 60.5, 120.0)]

        report = prosody.analyse(words, speech, total_sec=120.0)
        assert report.filler_count == 2
        assert report.filler_per_minute == pytest.approx(1.0)

    def test_a_measured_low_count_earns_good_where_a_transcript_count_cannot(self):
        """The asymmetry that justifies the whole module. Silence between the
        words, measured by the voice detector, is positive evidence that no
        filled pause happened — so this one is allowed to say "good", while the
        transcript version of the same number is only allowed to say
        "unmeasured"."""
        words = [w("a", 0.0, 20.0), w("b", 25.0, 60.0)]
        report = prosody.analyse(words, [Span(0.0, 20.0), Span(25.0, 60.0)], total_sec=60.0)

        filler = next(m for m in prosody.metrics(report) if m.key == "filled_pauses")
        assert filler.value == 0.0
        assert filler.verdict == "good"


class TestApiWiring:
    """Reaching the endpoint, because the interesting failure is in the seam.

    A route that assembles two analysers can be correct in both and still hand
    the page two filler numbers that disagree. Only a real request shows that.
    """

    def test_speech_spans_replace_the_transcript_filler_with_the_measured_one(
        self, scratch_operator
    ):
        from fastapi.testclient import TestClient

        from lighthouse.api import app

        # Said over 30s with a 0.8s "um" the transcriber dropped between word 5
        # and word 6, plus real silence either side of the answer.
        words = [{"text": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(40)]
        words[6]["start"] = 3.3
        speech = [{"start": 0.0, "end": 20.0}]

        body = {
            "transcript": " ".join(f"w{i}" for i in range(40)),
            "duration_sec": 30.0,
            "words": words,
            "speech": speech,
        }
        response = TestClient(app).post("/api/practice/answer", json=body)
        assert response.status_code == 200

        keys = {m["key"] for m in response.json()["delivery"]["metrics"]}
        assert "filled_pauses" in keys
        assert "articulation" in keys
        # Exactly one filler number reaches the page.
        assert "filler_density" not in keys

    def test_without_speech_spans_the_transcript_floor_is_what_ships(self, scratch_operator):
        from fastapi.testclient import TestClient

        from lighthouse.api import app

        body = {
            "transcript": " ".join(["word"] * 60),
            "duration_sec": 30.0,
        }
        response = TestClient(app).post("/api/practice/answer", json=body)
        assert response.status_code == 200

        keys = {m["key"] for m in response.json()["delivery"]["metrics"]}
        assert "filler_density" in keys
        assert "filled_pauses" not in keys
