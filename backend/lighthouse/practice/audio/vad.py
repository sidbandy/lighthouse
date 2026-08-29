"""Silero voice-activity detection: when was there voice, regardless of words.

This is one half of the filled-pause measurement. The transcriber says where the
words were; this says where the *sound* was; :mod:`practice.prosody` subtracts
one from the other and what is left is the "um".

Silero is a 2 MB ONNX model run through onnxruntime -- deliberately not the
``silero-vad`` pip package, which pulls torch. A 2 GB install to answer "is this
frame speech" is the trade this project exists to refuse.

**The post-processing is tuned for subtraction, not for playback.** Every
published VAD example pads its segments outward by 30 ms or so, because a
clipped word sounds bad. Padding here would be actively harmful: a segment wider
than the words inside it leaves residue at every single word boundary, and every
one of those would read as a filled pause. So padding is zero, the thresholds
are hysteretic to stop the boundary flapping mid-word, and short silences are
not bridged. Boundaries that are honest matter more than boundaries that sound
tidy, because nobody is listening to these -- they are being subtracted.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...core.config import get_settings
from ..prosody import Span
from .pcm import SAMPLE_RATE, Pcm

logger = logging.getLogger(__name__)

# Pinned to a release tag rather than master. The contract below -- window size,
# context length, state shape -- is a property of v5, and a model that silently
# becomes v6 under it would return plausible-looking numbers for the wrong
# reasons rather than failing.
MODEL_URL = (
    "https://raw.githubusercontent.com/snakers4/silero-vad/v5.1/"
    "src/silero_vad/data/silero_vad.onnx"
)

# Silero v5 consumes exactly this many new samples per step at 16 kHz.
WINDOW = 512

# ...but the tensor it wants is 576 long, because the model is fed the previous
# 64 samples as leading context on every step. This is not in the ONNX
# signature -- the input is declared [batch, any] -- and it is not optional:
# feeding a bare 512-sample window runs without error and returns a probability
# near zero for obvious speech, which looks like silence rather than like a bug.
# Found by feeding it a sentence and getting no voiced spans back.
CONTEXT = 64

# Hysteresis. Speech is entered at the high threshold and left at the low one,
# so a probability hovering around a single cut point cannot chop one word into
# three segments -- which would manufacture voiced gaps between the pieces.
ENTER_THRESHOLD = 0.50
EXIT_THRESHOLD = 0.35

# A "speech" run shorter than this is a click, a breath or a chair. Below it the
# detector is finding events, not voice.
MIN_SPEECH_SEC = 0.10

# Silences shorter than this stay inside the surrounding speech run. A stop
# consonant closes the vocal tract for ~50 ms, and treating that as the end of a
# segment would split "batched" into two and leave a gap between them.
MIN_SILENCE_SEC = 0.08


def _model_path() -> Path:
    return Path(get_settings().vad_model)


def availability() -> tuple[bool, str]:
    """Whether the detector can run, and what to do if it cannot.

    The reason is written to be pasted into a terminal, because "VAD
    unavailable" is a dead end and a command is not.
    """
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False, 'Install the voice extra: pip install -e "backend[voice]".'

    path = _model_path()
    if not path.exists():
        return False, (
            f"Download the voice detector to {path}: curl -sSL -o {path} "
            f"{MODEL_URL}"
        )
    return True, ""


_session = None


def _load():
    """Loaded once and kept. The model is 2 MB and the load costs more than the
    inference does, so paying it per request would dominate the measurement."""
    global _session
    if _session is None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        _session = ort.InferenceSession(
            str(_model_path()), options, providers=["CPUExecutionProvider"]
        )
    return _session


def probabilities(pcm: Pcm) -> list[float]:
    """Per-window speech probability.

    Two things are carried between steps and both are required. The LSTM
    ``state`` is the obvious one. The less obvious one is the trailing 64
    samples of audio, prepended to the next window as context -- without it the
    model returns near-zero for clear speech instead of failing, so the symptom
    is an answer that reads as silent.
    """
    import numpy as np

    session = _load()
    state = np.zeros((2, 1, 128), dtype=np.float32)
    context = np.zeros(CONTEXT, dtype=np.float32)
    rate = np.array(SAMPLE_RATE, dtype=np.int64)

    out: list[float] = []
    samples = pcm.samples
    for start in range(0, len(samples) - WINDOW + 1, WINDOW):
        chunk = samples[start : start + WINDOW]
        window = np.concatenate([context, chunk]).reshape(1, -1).astype(np.float32)
        prob, state = session.run(None, {"input": window, "state": state, "sr": rate})
        out.append(float(prob[0][0]))
        context = chunk[-CONTEXT:]
    return out


def _spans_from(probs: list[float], *, window_sec: float) -> list[Span]:
    """Hysteretic threshold over the probability track, then smoothing."""
    spans: list[Span] = []
    speaking = False
    start_idx = 0

    for i, p in enumerate(probs):
        if not speaking and p >= ENTER_THRESHOLD:
            speaking, start_idx = True, i
        elif speaking and p < EXIT_THRESHOLD:
            spans.append(Span(start_idx * window_sec, i * window_sec))
            speaking = False
    if speaking:
        spans.append(Span(start_idx * window_sec, len(probs) * window_sec))

    # Bridge the closures inside words before dropping the short runs, so a word
    # split by its own stop consonant is rejoined rather than deleted.
    bridged: list[Span] = []
    for span in spans:
        if bridged and (span.start - bridged[-1].end) < MIN_SILENCE_SEC:
            bridged[-1] = Span(bridged[-1].start, span.end)
        else:
            bridged.append(span)

    return [s for s in bridged if s.duration >= MIN_SPEECH_SEC]


def speech_spans(pcm: Pcm) -> list[Span]:
    """Voiced spans in seconds. Empty on any failure, which is a real answer.

    A detector that raises would take the whole analysis down with it; an empty
    list means "no acoustic evidence", which :mod:`practice.prosody` already
    handles by declining to report the measurements that need it.
    """
    try:
        probs = probabilities(pcm)
    except Exception:  # noqa: BLE001 - a broken model must not break the mock
        logger.exception("voice detection failed; continuing without acoustic evidence")
        return []
    return _spans_from(probs, window_sec=WINDOW / SAMPLE_RATE)
