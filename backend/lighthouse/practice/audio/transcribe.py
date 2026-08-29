"""whisper.cpp: an accurate transcript, and the word timings that matter more.

The transcript is the lesser half of what this returns. Browser speech
recognition already produces usable text live, and its text is what the operator
watches while they talk. What it cannot produce is *when each word was said*,
and without that there is no pause taxonomy, no articulation rate, and no
filled-pause detection -- every measurement in :mod:`practice.prosody` is
subtraction over timings.

whisper.cpp is a binary rather than a wheel, so it is found on PATH instead of
imported, and its absence is reported as a state rather than raised as an error.

**Tokens are not words.** whisper emits sub-word tokens: "internship" can arrive
as " intern" + "ship" with a timestamp on each. A token that begins a new word
carries a leading space and a continuation does not, which is what
:func:`merge_tokens` keys on. Skipping that step would double the word count,
halve the articulation rate, and invent a pause inside every long word.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ...core.config import get_settings
from ..delivery import Word
from .pcm import Pcm, to_wav_bytes

logger = logging.getLogger(__name__)

# Generous. Measured on an M3 with base.en-q5_1: ~19x faster than real time once
# the model is in the page cache, so a three-minute answer is about ten seconds.
# The first run after boot is far slower -- 20s of audio took 17s cold -- which is
# disk, not compute. This is the "something is wrong" bound, not the expected cost.
TIMEOUT_SEC = 300


def _binary() -> str | None:
    configured = get_settings().whisper_binary
    return shutil.which(configured) or shutil.which("whisper-cpp") or shutil.which("whisper")


def _model() -> Path:
    return Path(get_settings().whisper_model)


def availability() -> tuple[bool, str]:
    """Whether a transcript with timings can be produced, and how to enable it.

    Both halves are reported as a command to run, because a missing binary and a
    missing model need different commands and "transcriber unavailable" tells
    the operator neither.
    """
    if _binary() is None:
        return False, "Install whisper.cpp: brew install whisper-cpp."

    model = _model()
    if not model.exists():
        return False, (
            f"Download a whisper model to {model}: curl -sSL -o {model} "
            "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
            f"{model.name}"
        )
    return True, ""


def merge_tokens(tokens: list[tuple[str, float, float]]) -> list[Word]:
    """Sub-word tokens joined back into words, keeping first-start and last-end.

    A token that starts a word carries a leading space; a continuation does not.
    Punctuation attaches to the word it follows, which the pause taxonomy needs
    -- "shipped." is what tells it a clause ended there.
    """
    words: list[Word] = []
    for raw, start, end in tokens:
        text = raw.strip()
        if not text:
            continue
        starts_word = raw[:1].isspace() or not words
        if starts_word:
            words.append(Word(text=text, start=start, end=end))
        else:
            previous = words[-1]
            previous.text += text
            previous.end = end
    return words


def clamp(words: list[Word], duration_sec: float) -> list[Word]:
    """Hold word timings inside the audio they came from.

    whisper occasionally emits a trailing token that runs past the end of the
    file -- on a 20s recording the last word came back ending at 30s. Left
    alone that is a ten-second span of "voiced time with no word", which is a
    filled pause the size of a sentence, reported confidently, from a bug.
    """
    kept: list[Word] = []
    for word in words:
        start = min(max(word.start, 0.0), duration_sec)
        end = min(max(word.end, start), duration_sec)
        if end > start or not kept:
            kept.append(Word(text=word.text, start=start, end=end))
    return kept


def parse_output(payload: dict) -> tuple[str, list[Word]]:
    """Read whisper.cpp's ``-oj`` JSON into a transcript and word timings.

    ``offsets`` are milliseconds and are the field to trust; the ``timestamps``
    strings are the same numbers formatted for subtitles.
    """
    tokens: list[tuple[str, float, float]] = []
    for segment in payload.get("transcription", []):
        # Per-token offsets when the full output was requested, per-segment
        # otherwise. The distinction is the whole ballgame: a segment's offsets
        # tile the audio end to end, so every silence is absorbed into whichever
        # word preceded it and there are no gaps left to measure. Token offsets
        # have real boundaries with real silence between them.
        entries = segment.get("tokens") or [segment]
        for entry in entries:
            offsets = entry.get("offsets") or {}
            try:
                start = float(offsets["from"]) / 1000.0
                end = float(offsets["to"]) / 1000.0
            except (KeyError, TypeError, ValueError):
                continue
            if end < start:
                continue
            tokens.append((entry.get("text", ""), start, end))

    words = merge_tokens(tokens)
    transcript = " ".join(w.text for w in words).strip()
    return transcript, words


def transcribe(pcm: Pcm) -> tuple[str, list[Word]]:
    """Transcribe with word timings. Returns ``("", [])`` if it cannot.

    The audio is written to a temp file because whisper.cpp reads a path, and
    deleted in a ``finally`` whatever happens. Nothing survives the call --
    Practice promises the operator that what they said is not kept, and a
    stray file in the temp directory would be that promise quietly broken.
    """
    ok, _ = availability()
    if not ok:
        return "", []

    binary = _binary()
    handle, wav_path = tempfile.mkstemp(suffix=".wav", prefix="lighthouse-practice-")
    json_path = f"{wav_path}.json"
    try:
        with os.fdopen(handle, "wb") as f:
            f.write(to_wav_bytes(pcm))

        subprocess.run(
            [
                str(binary),
                "-m", str(_model()),
                "-f", wav_path,
                "-ojf",            # full JSON: per-token offsets, not per-segment
                "-np",             # no progress chatter on stderr
                "-nt",             # no timestamps inside the text itself
            ],
            check=True,
            capture_output=True,
            timeout=TIMEOUT_SEC,
        )
        with open(json_path, encoding="utf-8") as f:
            text, words = parse_output(json.load(f))
        return text, clamp(words, pcm.duration_sec)

    except subprocess.TimeoutExpired:
        logger.warning("whisper.cpp timed out after %ss; continuing without timings", TIMEOUT_SEC)
    except subprocess.CalledProcessError as exc:
        logger.warning("whisper.cpp exited %s: %s", exc.returncode, exc.stderr[-400:])
    except (OSError, json.JSONDecodeError):
        logger.exception("could not read whisper.cpp output")
    finally:
        for path in (wav_path, json_path):
            try:
                os.unlink(path)
            except OSError:
                pass

    return "", []
