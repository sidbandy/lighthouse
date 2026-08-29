"""The local voice pipeline: what is installed, and what that buys.

Two optional pieces, each useful on its own:

* **Silero VAD** (`onnxruntime`, a 2 MB model) says when sound was voiced.
* **whisper.cpp** (a binary) transcribes with per-word timings.

Together they measure filled pauses properly -- see :mod:`practice.prosody` for
why one without the other cannot. Separately, the detector still improves the
pause measurements and the transcriber still improves the transcript.

Neither being present is a supported state, not a degraded one. Practice
measures what a transcript can show, says which measurements it could not take,
and never fails because a model is missing. That is the same contract
:mod:`core.llm` holds for the provider layer, for the same reason: a tool that
stops working when an optional dependency is absent is a tool nobody trusts.

Everything runs on this machine. Audio is decoded in memory, and the one place a
file is written -- whisper.cpp reads a path, not a stream -- it is a temp file
that is deleted in a ``finally``. Nothing is retained.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import pcm, transcribe, vad

__all__ = ["Capability", "capability", "pcm", "transcribe", "vad"]


@dataclass(slots=True, frozen=True)
class Capability:
    """What this machine can actually measure, and how to widen it.

    Resolved before the operator records rather than after, because finding out
    that a ninety-second answer could not be analysed *after* giving it is the
    one failure this feature cannot afford.
    """

    voice_detector: bool
    transcriber: bool
    detector_reason: str
    transcriber_reason: str

    @property
    def measures_filled_pauses(self) -> bool:
        """Both, or neither. The measurement is the disagreement between them."""
        return self.voice_detector and self.transcriber

    @property
    def mode(self) -> str:
        if self.measures_filled_pauses:
            return "acoustic"
        return "transcript"

    def note(self) -> str:
        if self.measures_filled_pauses:
            return (
                "Filled pauses are measured from the audio on this machine. Nothing is "
                "uploaded and nothing is kept."
            )
        missing = []
        if not self.transcriber:
            missing.append(self.transcriber_reason)
        if not self.voice_detector:
            missing.append(self.detector_reason)
        return (
            "Delivery is measured from the transcript, so the filler count is a floor "
            "rather than a total — transcribers drop 'um'. To measure it from the sound: "
            + " ".join(missing)
        )


def capability() -> Capability:
    """Probe both pieces. Cheap enough to call per request, and it is, so that
    installing whisper.cpp takes effect without restarting the API."""
    detector_ok, detector_reason = vad.availability()
    transcriber_ok, transcriber_reason = transcribe.availability()
    return Capability(
        voice_detector=detector_ok,
        transcriber=transcriber_ok,
        detector_reason=detector_reason,
        transcriber_reason=transcriber_reason,
    )
