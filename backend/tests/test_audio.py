"""The local voice pipeline: decoding, detection, and the whisper adapter.

Almost none of this needs a model. The parts that would -- Silero's weights,
the whisper.cpp binary -- are reached through seams narrow enough to fake, so
the suite stays fast and runs on a machine where neither is installed. That is
also the point of the design: both are optional, so the tests have to prove the
absent case as carefully as the present one.

One test here exists because of a specific bug. Silero v5 is fed 512 new samples
plus the previous 64 as context, and the 64 are not in the ONNX signature.
Feeding a bare 512-sample window does not fail -- it returns a probability near
zero for clear speech, so a real answer comes back reading as silence. It cost
an afternoon, and the regression test pins the tensor width rather than the
output, because the output was plausible and only the width was wrong.
"""

import io
import wave

import pytest

from lighthouse.practice.audio import pcm as pcmmod
from lighthouse.practice.audio import transcribe, vad
from lighthouse.practice.prosody import Span


def make_wav(seconds=1.0, rate=16000, channels=1, width=2, value=1000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as h:
        h.setnchannels(channels)
        h.setsampwidth(width)
        h.setframerate(rate)
        frames = int(seconds * rate)
        sample = min(value, 2 ** (8 * width - 1) - 1)
        h.writeframes(sample.to_bytes(width, "little", signed=True) * frames * channels)
    return buf.getvalue()


class TestDecoding:
    def test_a_well_formed_wav_round_trips(self):
        decoded = pcmmod.decode_wav(make_wav(seconds=2.0))
        assert decoded.sample_rate == 16000
        assert decoded.duration_sec == pytest.approx(2.0, abs=0.01)
        again = pcmmod.decode_wav(pcmmod.to_wav_bytes(decoded))
        assert again.duration_sec == pytest.approx(decoded.duration_sec, abs=0.01)

    def test_the_wrong_sample_rate_is_refused_by_name(self):
        """Resampling silently would leave every timestamp wrong by the ratio,
        and every measurement downstream is a timestamp. The message says which
        rate arrived so nobody goes looking at their microphone."""
        with pytest.raises(pcmmod.AudioError, match="48000 Hz"):
            pcmmod.decode_wav(make_wav(rate=48000))

    def test_stereo_is_refused(self):
        with pytest.raises(pcmmod.AudioError, match="2 channels"):
            pcmmod.decode_wav(make_wav(channels=2))

    def test_eight_bit_audio_is_refused(self):
        with pytest.raises(pcmmod.AudioError, match="8-bit"):
            pcmmod.decode_wav(make_wav(width=1))

    def test_a_fragment_is_refused_rather_than_measured(self):
        with pytest.raises(pcmmod.AudioError, match="Too short"):
            pcmmod.decode_wav(make_wav(seconds=0.2))

    def test_junk_is_refused_without_raising_something_unreadable(self):
        with pytest.raises(pcmmod.AudioError, match="Not a readable WAV"):
            pcmmod.decode_wav(b"this is not a wav file at all")


class TestModelContract:
    """The bug that returned silence for speech."""

    def test_every_window_is_fed_with_its_leading_context(self, monkeypatch):
        import numpy as np

        seen = []

        class FakeSession:
            def run(self, _outputs, feeds):
                seen.append(np.array(feeds["input"])[0].copy())
                return [np.array([[0.9]], dtype=np.float32), feeds["state"]]

        monkeypatch.setattr(vad, "_load", lambda: FakeSession())
        pcm = pcmmod.decode_wav(make_wav(seconds=1.0))
        vad.probabilities(pcm)

        assert seen, "the detector was never fed anything"
        # 512 new samples plus 64 carried: the width the model actually wants.
        assert all(len(w) == vad.WINDOW + vad.CONTEXT for w in seen)

        # And the carried part really is the tail of the previous window, not
        # zeros -- continuity is what the LSTM is reading.
        for previous, current in zip(seen, seen[1:], strict=False):
            assert np.array_equal(current[: vad.CONTEXT], previous[-vad.CONTEXT :])

    def test_the_first_window_leads_with_silence_rather_than_garbage(self, monkeypatch):
        import numpy as np

        seen = []

        class FakeSession:
            def run(self, _outputs, feeds):
                seen.append(np.array(feeds["input"])[0].copy())
                return [np.array([[0.1]], dtype=np.float32), feeds["state"]]

        monkeypatch.setattr(vad, "_load", lambda: FakeSession())
        vad.probabilities(pcmmod.decode_wav(make_wav(seconds=0.6)))
        assert not seen[0][: vad.CONTEXT].any()


class TestSpanShaping:
    """Post-processing, tuned for subtraction rather than for playback."""

    def _spans(self, probs):
        return vad._spans_from(probs, window_sec=0.032)

    def test_a_clear_run_of_speech_becomes_one_span(self):
        spans = self._spans([0.0] * 5 + [0.9] * 20 + [0.0] * 5)
        assert len(spans) == 1
        assert spans[0].start == pytest.approx(5 * 0.032)

    def test_hysteresis_keeps_a_wobbling_probability_as_one_span(self):
        """A probability hovering at a single cut point would chop one word into
        three, and the gaps between the pieces would read as filled pauses."""
        spans = self._spans([0.9, 0.45, 0.9, 0.42, 0.9] * 4 + [0.0] * 5)
        assert len(spans) == 1

    def test_a_stop_consonant_does_not_split_a_word(self):
        """~50ms of closure inside "batched" is not the end of a segment."""
        spans = self._spans([0.9] * 10 + [0.0] * 2 + [0.9] * 10 + [0.0] * 5)
        assert len(spans) == 1

    def test_a_real_silence_does_split_the_run(self):
        spans = self._spans([0.9] * 10 + [0.0] * 20 + [0.9] * 10)
        assert len(spans) == 2

    def test_a_click_is_not_speech(self):
        assert self._spans([0.0] * 5 + [0.9] * 2 + [0.0] * 5) == []

    def test_speech_running_to_the_end_is_still_closed(self):
        spans = self._spans([0.0] * 3 + [0.9] * 20)
        assert len(spans) == 1
        assert spans[0].end == pytest.approx(23 * 0.032)

    def test_silence_throughout_yields_nothing(self):
        assert self._spans([0.01] * 50) == []


class TestWhisperAdapter:
    def test_subword_tokens_are_joined_back_into_words(self):
        """whisper emits " intern" + "ship". Left alone that is two words with a
        gap between them: the word count doubles, the articulation rate halves,
        and a pause is invented inside every long word."""
        words = transcribe.merge_tokens(
            [(" intern", 0.0, 0.3), ("ship", 0.3, 0.5), (" was", 0.6, 0.8)]
        )
        assert [w.text for w in words] == ["internship", "was"]
        assert words[0].start == 0.0 and words[0].end == 0.5

    def test_punctuation_stays_attached_to_its_word(self):
        """The pause taxonomy reads it: "shipped." is what marks a clause end."""
        words = transcribe.merge_tokens([(" shipped", 0.0, 0.4), (".", 0.4, 0.45)])
        assert [w.text for w in words] == ["shipped."]

    def test_a_leading_token_without_a_space_still_starts_the_transcript(self):
        words = transcribe.merge_tokens([("At", 0.0, 0.2), (" first", 0.2, 0.5)])
        assert [w.text for w in words] == ["At", "first"]

    def test_real_whisper_json_becomes_transcript_and_timings(self):
        payload = {
            "transcription": [
                {"offsets": {"from": 0, "to": 400}, "text": " I"},
                {"offsets": {"from": 400, "to": 900}, "text": " re"},
                {"offsets": {"from": 900, "to": 1200}, "text": "wrote"},
                {"offsets": {"from": 1300, "to": 1800}, "text": " it."},
            ]
        }
        text, words = transcribe.parse_output(payload)
        assert text == "I rewrote it."
        assert [w.text for w in words] == ["I", "rewrote", "it."]
        assert words[1].start == pytest.approx(0.4)
        assert words[1].end == pytest.approx(1.2)

    def test_a_segment_with_no_offsets_is_skipped_not_guessed(self):
        payload = {
            "transcription": [
                {"text": " orphan"},
                {"offsets": {"from": 0, "to": 100}, "text": " real"},
            ]
        }
        text, words = transcribe.parse_output(payload)
        assert [w.text for w in words] == ["real"]
        assert text == "real"

    def test_empty_output_is_empty_rather_than_an_error(self):
        assert transcribe.parse_output({}) == ("", [])


class TestCapability:
    def test_the_absent_case_names_a_command_rather_than_a_state(self, monkeypatch):
        """"Transcriber unavailable" is a dead end. A command is not."""
        from lighthouse.practice import audio

        monkeypatch.setattr(vad, "availability", lambda: (True, ""))
        monkeypatch.setattr(
            transcribe,
            "availability",
            lambda: (False, "Install whisper.cpp: brew install whisper-cpp."),
        )
        cap = audio.capability()
        assert not cap.measures_filled_pauses
        assert cap.mode == "transcript"
        assert "brew install whisper-cpp" in cap.note()
        assert "floor" in cap.note()

    def test_both_present_promises_the_measurement_and_the_privacy(self, monkeypatch):
        from lighthouse.practice import audio

        monkeypatch.setattr(vad, "availability", lambda: (True, ""))
        monkeypatch.setattr(transcribe, "availability", lambda: (True, ""))
        cap = audio.capability()
        assert cap.measures_filled_pauses
        assert cap.mode == "acoustic"
        assert "nothing is kept" in cap.note()

    def test_one_without_the_other_does_not_claim_the_measurement(self, monkeypatch):
        """The filled-pause count is the disagreement between two signals. One
        signal cannot disagree with anything."""
        from lighthouse.practice import audio

        monkeypatch.setattr(vad, "availability", lambda: (False, "install the voice extra."))
        monkeypatch.setattr(transcribe, "availability", lambda: (True, ""))
        assert not audio.capability().measures_filled_pauses


class TestTimingHygiene:
    """Two defects found by running real audio through, not by reading code."""

    def test_a_word_running_past_the_end_is_clamped(self):
        """On a 20s recording whisper returned a final word ending at 30s. Left
        alone that is a ten-second span of voiced-time-with-no-word: a filled
        pause the size of a sentence, reported confidently, out of a bug."""
        from lighthouse.practice.delivery import Word

        clamped = transcribe.clamp(
            [Word("fine", 0.0, 1.0), Word("overrun", 1.0, 30.0)], duration_sec=20.31
        )
        assert clamped[-1].end == pytest.approx(20.31)
        assert all(w.end <= 20.31 for w in clamped)

    def test_words_placed_outside_the_audio_are_dropped_not_kept_at_zero_length(self):
        from lighthouse.practice.delivery import Word

        clamped = transcribe.clamp(
            [Word("real", 0.0, 1.0), Word("ghost", 25.0, 25.0)], duration_sec=20.0
        )
        assert [w.text for w in clamped] == ["real"]

    def test_the_rate_uses_the_spoken_word_count_not_the_placeable_one(self):
        """Dropping unplaceable words from the timings must not also drop them
        from the rate, or the page shows two different word counts."""
        from lighthouse.practice import prosody
        from lighthouse.practice.delivery import Word

        words = [Word("a", 0.0, 10.0)]
        report = prosody.fluency(words, [Span(0, 10)], total_sec=60.0, word_count=60)
        assert report.word_count == 60
        assert round(report.speaking_rate) == 60
