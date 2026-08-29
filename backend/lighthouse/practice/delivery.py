"""Layer 1 feedback: how the answer was delivered. No model, ever.

Filler density, pace, silences and length are arithmetic over a transcript.
Computing them locally means they work with no key, no network and no quota, and
that they are identical every time — which is what makes a trend across six
sessions mean anything. A number that moves because a model was in a different
mood is not a trend.

Every threshold here is a published interview-coaching convention rather than
something fitted to data this project does not have, and each is stated once,
in the open, with the reason next to it. The operator can disagree with any of
them and see exactly what they are disagreeing with.

Nothing in this module judges *content*. That is Layer 2 and Layer 3, and they
are separate on purpose: a well-structured answer delivered badly and a rambling
answer delivered smoothly need different advice.

**One measure here is a floor rather than a total.** Filled pauses are counted
by looking for them in the transcript, and every transcriber drops them, so a
low count means the transcript was clean and not that the answer was. A high
count is still safe to act on -- the true number can only be larger -- but a low
one is reported as unmeasured rather than as good. :mod:`practice.prosody`
measures it properly, from the audio, and supersedes this one when it can.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# The words people reach for while thinking. "Like" and "so" are included only
# as standalone fillers -- "things like this" and "so I built" are ordinary
# English and counting them would make the number noise.
FILLERS: tuple[str, ...] = (
    "um", "uh", "erm", "ah", "hmm", "mmm",
    "like", "basically", "actually", "literally", "honestly",
    "kind of", "sort of", "you know", "i mean", "i guess",
)

# Conversational speech sits around 130-160 words per minute. Nervousness pushes
# people well past 180, which is the single most common delivery problem in a
# first mock and the easiest to fix once it is named.
WPM_LOW = 130
WPM_HIGH = 160
WPM_RUSHED = 185

# A behavioural answer that lands is about a minute and a half. Under 45 seconds
# is usually a missing Result; over three minutes has stopped being an answer.
DURATION_LOW_SEC = 75
DURATION_HIGH_SEC = 150
DURATION_RAMBLING_SEC = 210

# A pause this long reads as being stuck rather than thinking.
LONG_SILENCE_SEC = 5.0

# Filler density above this is what a listener starts noticing. Below it, the
# occasional "um" is just speech.
FILLER_PER_MINUTE_HIGH = 6.0

# One name per metric, shared by the report and by the trend that reads stored
# sessions back. Two copies would drift, and a trend labelled differently from
# the number it tracks reads as two separate measurements.
METRIC_LABELS: dict[str, str] = {
    "wpm": "Pace",
    "filler_density": "Filler words",
    "duration": "Length",
    "silences": "Long pauses",
}


@dataclass(slots=True)
class Word:
    """One transcribed word with its timing, as whisper.cpp emits."""

    text: str
    start: float
    end: float


@dataclass(slots=True)
class DeliveryMetric:
    """One measurement, with the band it is being judged against.

    ``ideal`` travels with ``value`` so the operator is never shown a bare
    number and left to guess whether it is good.
    """

    key: str
    label: str
    value: float
    unit: str
    ideal: str
    verdict: str  # good | watch | off | unknown
    detail: str

    @property
    def rounded(self) -> float:
        return round(self.value, 1)


@dataclass(slots=True)
class DeliveryReport:
    duration_sec: float
    word_count: int
    metrics: list[DeliveryMetric] = field(default_factory=list)
    filler_examples: list[str] = field(default_factory=list)

    @property
    def is_measurable(self) -> bool:
        """Below a few seconds there is nothing to measure, and reporting
        "220 wpm" off four words would be arithmetic pretending to be insight."""
        return self.duration_sec >= 10 and self.word_count >= 20

    def by_key(self, key: str) -> DeliveryMetric | None:
        return next((m for m in self.metrics if m.key == key), None)

    def summary(self) -> str:
        if not self.is_measurable:
            return "Too short to measure. Answer for at least fifteen seconds."
        off = [m for m in self.metrics if m.verdict == "off"]
        if off:
            return "Worth working on: " + ", ".join(m.label.lower() for m in off) + "."
        # "Nothing was off" and "everything was good" are different claims when
        # one of the measures could not be taken. Saying the second while the
        # filler count is unmeasured is the flattery this layer exists to avoid.
        unknown = [m for m in self.metrics if m.verdict == "unknown"]
        if unknown:
            return (
                "Nothing off in what could be measured — but "
                + ", ".join(m.label.lower() for m in unknown)
                + " cannot be judged from a transcript."
            )
        return "Delivery is in a good band on every measure."


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z' ]+", " ", text.lower())


def count_fillers(transcript: str) -> tuple[int, list[str]]:
    """Filler occurrences, and the most frequent ones in this transcript.

    Longest fillers are *matched* first and removed, so "you know" does not also
    register as two words and "i mean" does not double-count. The examples are
    then ordered by how often each occurred, because "um ×7" is the one worth
    knowing about and matching order would have buried it under a single
    "basically".
    """
    text = " " + re.sub(r"\s+", " ", _normalise(transcript)) + " "
    counts: list[tuple[str, int]] = []

    for filler in sorted(FILLERS, key=len, reverse=True):
        pattern = re.compile(rf"(?<![a-z']){re.escape(filler)}(?![a-z'])")
        hits = pattern.findall(text)
        if hits:
            counts.append((filler, len(hits)))
            text = pattern.sub(" ", text)

    counts.sort(key=lambda pair: (-pair[1], pair[0]))
    return sum(n for _, n in counts), [f"{word} ×{n}" for word, n in counts]


def longest_silence(words: list[Word]) -> float:
    """The longest gap between consecutive words."""
    if len(words) < 2:
        return 0.0
    return max(
        (b.start - a.end for a, b in zip(words, words[1:], strict=False)),
        default=0.0,
    )


def count_long_silences(words: list[Word], threshold: float = LONG_SILENCE_SEC) -> int:
    if len(words) < 2:
        return 0
    return sum(
        1 for a, b in zip(words, words[1:], strict=False) if (b.start - a.end) >= threshold
    )


def analyse(
    transcript: str,
    *,
    duration_sec: float,
    words: list[Word] | None = None,
) -> DeliveryReport:
    """Measure one spoken answer. Deterministic, offline, and repeatable.

    ``words`` carries timings when whisper.cpp has produced them; without it the
    silence measures are simply absent rather than estimated, because a guessed
    pause is worse than no pause.
    """
    spoken = [w for w in _normalise(transcript).split() if w]
    word_count = len(spoken)
    report = DeliveryReport(duration_sec=round(duration_sec, 1), word_count=word_count)

    if not report.is_measurable:
        return report

    minutes = duration_sec / 60.0
    filler_count, examples = count_fillers(transcript)
    report.filler_examples = examples[:6]

    wpm = word_count / minutes if minutes else 0.0
    if wpm >= WPM_RUSHED:
        verdict, detail = "off", (
            f"{round(wpm)} words a minute. Rushing is the most common tell in a first "
            "mock — the fix is to finish each sentence before starting the next, not "
            "to think faster."
        )
    elif WPM_LOW <= wpm <= WPM_HIGH:
        verdict, detail = "good", f"{round(wpm)} words a minute, right in the conversational band."
    else:
        verdict, detail = "watch", (
            f"{round(wpm)} words a minute, "
            + ("a little fast." if wpm > WPM_HIGH else "a little slow, which can read as unsure.")
        )
    report.metrics.append(
        DeliveryMetric(
            key="wpm",
            label=METRIC_LABELS["wpm"],
            value=wpm,
            unit="words/min",
            ideal=f"{WPM_LOW}–{WPM_HIGH}",
            verdict=verdict,
            detail=detail,
        )
    )

    # A lexical count is a *floor*, never a total. Every transcriber this runs
    # on discards filled pauses -- browser speech recognition treats them as
    # noise, and Whisper was trained on cleaned subtitles -- so what survives
    # into the transcript is an unpredictable fraction of what was said.
    #
    # That asymmetry decides the verdicts. A high count is safe to act on,
    # because the real number can only be higher. A low count proves nothing at
    # all, and calling it "good" would be this project telling the operator they
    # are better than they are on the most actionable metric it has.
    # :mod:`practice.prosody` measures the real number from the audio; until
    # those spans exist, the honest verdict for a low count is that it is
    # unmeasured.
    density = filler_count / minutes if minutes else 0.0
    if density >= FILLER_PER_MINUTE_HIGH:
        verdict, detail = "off", (
            f"At least {filler_count} fillers in {round(duration_sec)}s, and the transcript "
            "drops some. A silent pause costs you nothing and sounds considered; an 'um' is "
            "the same pause with a noise on it."
        )
    elif density >= FILLER_PER_MINUTE_HIGH / 2:
        verdict, detail = "watch", (
            f"At least {filler_count} fillers — already noticeable, and that is a floor "
            "rather than a total."
        )
    else:
        verdict, detail = "unknown", (
            f"Only {filler_count} made it into the transcript, which is not the same as only "
            f"{filler_count} being said — transcribers drop 'um' as noise. This one cannot be "
            "read as clean until it is measured from the audio."
        )
    report.metrics.append(
        DeliveryMetric(
            key="filler_density",
            label=METRIC_LABELS["filler_density"],
            value=density,
            unit="per min",
            ideal=f"under {FILLER_PER_MINUTE_HIGH:.0f}",
            verdict=verdict,
            detail=detail,
        )
    )

    if duration_sec >= DURATION_RAMBLING_SEC:
        verdict, detail = "off", (
            f"{round(duration_sec)}s. Past about three minutes an interviewer has stopped "
            "following the thread and is waiting for the Result."
        )
    elif DURATION_LOW_SEC <= duration_sec <= DURATION_HIGH_SEC:
        verdict, detail = "good", f"{round(duration_sec)}s, a good length for a behavioural answer."
    elif duration_sec < DURATION_LOW_SEC:
        verdict, detail = "watch", (
            f"{round(duration_sec)}s is short. Usually the Result is missing rather than the story."
        )
    else:
        verdict, detail = "watch", f"{round(duration_sec)}s, running slightly long."
    report.metrics.append(
        DeliveryMetric(
            key="duration",
            label=METRIC_LABELS["duration"],
            value=duration_sec,
            unit="sec",
            ideal=f"{DURATION_LOW_SEC}–{DURATION_HIGH_SEC}s",
            verdict=verdict,
            detail=detail,
        )
    )

    if words:
        longest = longest_silence(words)
        count = count_long_silences(words)
        if count >= 3:
            verdict, detail = "off", (
                f"{count} pauses over {LONG_SILENCE_SEC:.0f}s, longest {longest:.1f}s. "
                "Usually means the story is being assembled live — worth outlining it once "
                "before the next run."
            )
        elif count:
            verdict, detail = "watch", f"{count} long pause, {longest:.1f}s at the longest."
        else:
            verdict, detail = "good", "No long stalls."
        report.metrics.append(
            DeliveryMetric(
                key="silences",
                label=METRIC_LABELS["silences"],
                value=float(count),
                unit="over 5s",
                ideal="0–1",
                verdict=verdict,
                detail=detail,
            )
        )

    return report


@dataclass(slots=True)
class Trend:
    """One metric across sessions. The operator against themselves, which is the
    only baseline that means anything here."""

    key: str
    label: str
    first: float
    latest: float
    sessions: int

    @property
    def change(self) -> float:
        return self.latest - self.first

    def statement(self) -> str:
        if self.sessions < 3:
            return f"{self.sessions} sessions — not a trend yet."
        if abs(self.change) < 0.05 * max(abs(self.first), 1):
            return f"Flat across {self.sessions} sessions."
        direction = "down" if self.change < 0 else "up"
        pct = abs(self.change) / max(abs(self.first), 1e-9) * 100
        return f"{direction} {round(pct)}% across {self.sessions} sessions."


def trend(key: str, label: str, values: list[float]) -> Trend | None:
    """Track one metric over time. Two points are not a trend and say so."""
    if len(values) < 2:
        return None
    return Trend(key=key, label=label, first=values[0], latest=values[-1], sessions=len(values))
