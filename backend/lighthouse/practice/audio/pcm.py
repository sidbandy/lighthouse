"""Decoding the one audio format this pipeline accepts, and rejecting the rest.

The browser sends 16 kHz mono 16-bit PCM WAV because that is exactly what both
whisper.cpp and Silero want, and producing it in the page removes ffmpeg from
the dependency list entirely. A ``MediaRecorder`` blob would be webm/opus and
would need transcoding; Web Audio can hand over raw samples instead, so it does.

Validation is strict and the errors name the actual problem. Silently resampling
a 48 kHz file would make every timestamp wrong by a factor of three, and every
measurement downstream is a timestamp.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1

# Below this there is no answer to measure, and whisper on a fragment produces
# confident nonsense.
MIN_SECONDS = 0.5


class AudioError(ValueError):
    """The upload was not the format this pipeline accepts."""


@dataclass(slots=True)
class Pcm:
    """Mono float32 samples in [-1, 1], with the rate they were taken at."""

    samples: np.ndarray
    sample_rate: int

    @property
    def duration_sec(self) -> float:
        return len(self.samples) / self.sample_rate if self.sample_rate else 0.0


def decode_wav(payload: bytes) -> Pcm:
    """Read a 16 kHz mono 16-bit WAV into float32 samples.

    Raises :class:`AudioError` with a specific message on anything else, because
    "could not process audio" sends someone to look at their microphone when the
    real problem is a sample rate.
    """
    try:
        with wave.open(io.BytesIO(payload), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except wave.Error as exc:
        raise AudioError(f"Not a readable WAV file: {exc}") from exc

    if channels != CHANNELS:
        raise AudioError(f"Expected mono audio, got {channels} channels.")
    if width != SAMPLE_WIDTH:
        raise AudioError(f"Expected 16-bit samples, got {width * 8}-bit.")
    if rate != SAMPLE_RATE:
        raise AudioError(
            f"Expected {SAMPLE_RATE} Hz, got {rate} Hz. Every timestamp downstream "
            "depends on this, so it is rejected rather than resampled."
        )

    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if len(samples) < MIN_SECONDS * SAMPLE_RATE:
        raise AudioError("Too short to measure — under half a second of audio.")

    return Pcm(samples=samples, sample_rate=rate)


def to_wav_bytes(pcm: Pcm) -> bytes:
    """Back to a WAV file, for the transcriber that reads paths rather than
    streams."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(SAMPLE_WIDTH)
        handle.setframerate(pcm.sample_rate)
        clipped = np.clip(pcm.samples, -1.0, 1.0)
        handle.writeframes((clipped * 32767.0).astype("<i2").tobytes())
    return buffer.getvalue()
