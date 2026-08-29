"""Layer 1, measured from the signal rather than from the words.

This module exists because the filler count in :mod:`practice.delivery` is
systematically wrong in the direction that flatters, and cannot be fixed by
counting harder.

**Why counting words cannot work.** Browser speech recognition treats "um" as
noise and drops it. Whisper is trained largely on cleaned subtitles and drops it
too. So a lexical filler count measures the fillers that survived
transcription, which is a small and unpredictable fraction of the fillers that
were said. Reporting that as "7 fillers" tells the operator they are better than
they are, on the single most actionable metric in the layer.

**What works instead.** A filled pause is *voiced time that produced no word* --
and the transcriber's habit of dropping it is exactly what makes it findable.
Intersect two independent signals:

* a voice-activity detector, which knows when sound was voiced, and
* a transcriber's word timings, which know when a word was said

and the residue -- voiced, but no word assigned -- is where the "um" was. The
transcriber's blind spot becomes the detector.

Nothing here imports an audio library, a model, or numpy. It is arithmetic over
two lists of intervals, so it is testable without a microphone, identical on
every run, and unaffected by which transcriber produced the timings. The pieces
that do touch audio are adapters that produce these intervals and nothing more.

**What this does not claim.** A voiced gap is voiced time the transcriber did
not account for. That is usually a filled pause; it can also be a laugh, a
throat clear, or a word the transcriber missed. The measurement is reported as
what it is, and the operator can play the span back and hear which it was --
the same reason the résumé checker shows the parse rather than describing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .delivery import (
    FILLER_PER_MINUTE_HIGH,
    WPM_HIGH,
    WPM_LOW,
    WPM_RUSHED,
    DeliveryMetric,
    Word,
)

# A voiced gap shorter than this is inside the alignment error of the
# transcriber that produced the word timings -- whisper's DTW alignment is good
# to roughly a tenth of a second, so anything below that is slop, not sound.
MIN_VOICED_GAP_SEC = 0.18

# Above this a voiced span is a held note, a laugh, or a word that failed to
# transcribe. Filled pauses in spontaneous speech cluster well under a second;
# the tail is real but thin, and the honest move at the top end is to report the
# span without calling it a filler.
MAX_FILLER_SEC = 1.50

# A silent gap below this is the ordinary rhythm of speech -- the break between
# any two words. Only gaps above it are pauses anyone perceives.
MIN_PAUSE_SEC = 0.25

# Punctuation the transcriber emits at a clause or sentence boundary. A pause
# after one of these is phrasing; a pause without one is mid-clause.
_BOUNDARY_CHARS = ".?!,;:—"

# Function words that end nothing. A pause straight after "the" or "of" is the
# clearest word-searching signal in speech, because the speaker has committed to
# a phrase and not yet found its head.
_DANGLING_WORDS = frozenset(
    """
    the a an of to in on at for with by from as and or but so that this these those
    is are was were be been being have has had my our your their its it he she they we i
    """.split()
)


class PauseKind(StrEnum):
    JUNCTURE = "juncture"
    HESITATION = "hesitation"


PAUSE_KIND_LABELS: dict[PauseKind, str] = {
    PauseKind.JUNCTURE: "at a clause boundary",
    PauseKind.HESITATION: "mid-clause",
}


@dataclass(slots=True, frozen=True)
class Span:
    """A half-open interval of time, in seconds."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(slots=True)
class VoicedGap:
    """Voiced time the transcriber assigned no word to.

    ``is_probable_filler`` is a duration band, not a classifier, and it is
    reported next to the span so the operator can play it back and disagree.
    """

    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def is_probable_filler(self) -> bool:
        return MIN_VOICED_GAP_SEC <= self.duration <= MAX_FILLER_SEC

    def statement(self) -> str:
        at = f"{int(self.start // 60)}:{int(self.start % 60):02d}"
        if self.is_probable_filler:
            return f"{at} — {self.duration:.1f}s of voice with no word in it."
        return f"{at} — {self.duration:.1f}s voiced and untranscribed; longer than a filler."


@dataclass(slots=True)
class Pause:
    """A silence between two transcribed words, and why it is being called what
    it is called. ``rule`` travels with ``kind`` so the classification is
    inspectable rather than asserted."""

    start: float
    end: float
    kind: PauseKind
    rule: str
    after_word: str
    before_word: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def merge(spans: list[Span]) -> list[Span]:
    """Overlapping or touching intervals collapsed into one each."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s.start, s.end))
    out = [ordered[0]]
    for span in ordered[1:]:
        last = out[-1]
        if span.start <= last.end:
            if span.end > last.end:
                out[-1] = Span(last.start, span.end)
        else:
            out.append(span)
    return out


def subtract(spans: list[Span], holes: list[Span]) -> list[Span]:
    """What is left of ``spans`` once every ``holes`` interval is removed.

    This is the whole detector in one function: speech minus words is the
    voiced time nothing was transcribed for.
    """
    remaining = merge(spans)
    for hole in merge(holes):
        nxt: list[Span] = []
        for span in remaining:
            if hole.end <= span.start or hole.start >= span.end:
                nxt.append(span)
                continue
            if hole.start > span.start:
                nxt.append(Span(span.start, hole.start))
            if hole.end < span.end:
                nxt.append(Span(hole.end, span.end))
        remaining = nxt
    return [s for s in remaining if s.duration > 0]


def word_spans(words: list[Word]) -> list[Span]:
    return [Span(w.start, w.end) for w in words]


def voiced_gaps(
    speech: list[Span],
    words: list[Word],
    *,
    min_sec: float = MIN_VOICED_GAP_SEC,
) -> list[VoicedGap]:
    """Voiced spans with no word in them, longest first.

    ``speech`` comes from the voice-activity detector and ``words`` from the
    transcriber. They are independent measurements of the same audio, which is
    the only reason their disagreement means anything.
    """
    residue = subtract(speech, word_spans(words))
    gaps = [VoicedGap(s.start, s.end) for s in residue if s.duration >= min_sec]
    gaps.sort(key=lambda g: -g.duration)
    return gaps


def classify_pause(before: Word, after: Word) -> Pause:
    """Name the silence between two words, and record which rule named it.

    Juncture is only ever claimed on positive evidence -- the transcriber
    punctuated the boundary. Everything else is mid-clause, because "no evidence
    of a boundary" is not the same as "evidence of no boundary" and the honest
    default is the one that does not flatter.
    """
    tail = before.text.strip()
    stripped = tail.rstrip(_BOUNDARY_CHARS)

    if tail and tail != stripped:
        return Pause(
            start=before.end,
            end=after.start,
            kind=PauseKind.JUNCTURE,
            rule=f"the transcriber punctuated after {stripped or tail!r}",
            after_word=tail,
            before_word=after.text,
        )

    bare = stripped.lower().strip("'\"")
    if bare in _DANGLING_WORDS:
        return Pause(
            start=before.end,
            end=after.start,
            kind=PauseKind.HESITATION,
            rule=f"paused straight after {bare!r}, which ends no phrase",
            after_word=tail,
            before_word=after.text,
        )

    return Pause(
        start=before.end,
        end=after.start,
        kind=PauseKind.HESITATION,
        rule="no clause boundary was marked here",
        after_word=tail,
        before_word=after.text,
    )


def pauses(words: list[Word], *, min_sec: float = MIN_PAUSE_SEC) -> list[Pause]:
    """Every perceptible silence between consecutive words, in time order."""
    out: list[Pause] = []
    for before, after in zip(words, words[1:], strict=False):
        if (after.start - before.end) >= min_sec:
            out.append(classify_pause(before, after))
    return out


@dataclass(slots=True)
class FluencyReport:
    """The two rates that separate "fast" from "fast in bursts".

    Speaking rate counts the pauses; articulation rate does not. Someone at 140
    words a minute overall who articulates at 210 is not a fast talker -- they
    are a normal talker stopping constantly to find the next word, and the fix
    for that is preparation, not slowing down. One number cannot tell those
    apart, which is why two are reported.
    """

    word_count: int
    total_sec: float
    phonation_sec: float

    @property
    def speaking_rate(self) -> float:
        return self.word_count / (self.total_sec / 60.0) if self.total_sec > 0 else 0.0

    @property
    def articulation_rate(self) -> float:
        return (
            self.word_count / (self.phonation_sec / 60.0) if self.phonation_sec > 0 else 0.0
        )

    @property
    def phonation_ratio(self) -> float:
        """Share of the answer that was actually sound. A standard fluency
        measure, and the plainest way to say "you paused a lot"."""
        return self.phonation_sec / self.total_sec if self.total_sec > 0 else 0.0

    def statement(self) -> str:
        if self.total_sec <= 0 or not self.word_count:
            return "Nothing to measure."
        gap = self.articulation_rate - self.speaking_rate
        if gap < 15:
            return (
                f"{round(self.speaking_rate)} words a minute, and {round(self.articulation_rate)} "
                "while actually speaking — steady, with little time lost to pauses."
            )
        return (
            f"{round(self.speaking_rate)} words a minute overall but "
            f"{round(self.articulation_rate)} while actually speaking. You were talking at "
            f"pace and stopping often — {round((1 - self.phonation_ratio) * 100)}% of the "
            "answer was silence."
        )


def fluency(
    words: list[Word],
    speech: list[Span],
    *,
    total_sec: float,
    word_count: int | None = None,
) -> FluencyReport:
    """Speaking rate against articulation rate, over measured voiced time.

    ``word_count`` overrides ``len(words)`` because they can legitimately
    differ: a transcriber sometimes returns a word it could not place in time,
    and such a word is dropped from the timings while still being a word that
    was said. Counting only the placeable ones would quietly understate every
    rate here, and disagree with the word count the transcript reports.
    """
    phonation = sum(s.duration for s in merge(speech))
    return FluencyReport(
        word_count=len(words) if word_count is None else word_count,
        total_sec=total_sec,
        phonation_sec=phonation,
    )


@dataclass(slots=True)
class ProsodyReport:
    """Everything derivable from intervals, with the spans kept.

    The spans are the point. A count of filled pauses is a number to argue with;
    a list of timestamps is something to play back, and the operator hearing
    their own "um" at 1:04 is worth more than any figure this module produces.
    """

    gaps: list[VoicedGap]
    pauses: list[Pause]
    fluency: FluencyReport

    @property
    def filler_count(self) -> int:
        return sum(1 for g in self.gaps if g.is_probable_filler)

    @property
    def filler_per_minute(self) -> float:
        minutes = self.fluency.total_sec / 60.0
        return self.filler_count / minutes if minutes > 0 else 0.0

    @property
    def juncture_pauses(self) -> int:
        return sum(1 for p in self.pauses if p.kind is PauseKind.JUNCTURE)

    @property
    def hesitation_pauses(self) -> int:
        return sum(1 for p in self.pauses if p.kind is PauseKind.HESITATION)

    def pause_statement(self) -> str:
        if not self.pauses:
            return "No pauses long enough to notice."
        total = len(self.pauses)
        if not self.hesitation_pauses:
            return f"{total} pauses, every one of them at a clause boundary. That is phrasing."
        if not self.juncture_pauses:
            return (
                f"{total} pauses, none at a clause boundary — all of them landed mid-phrase, "
                "which is what searching for a word sounds like."
            )
        return (
            f"{total} pauses: {self.juncture_pauses} at a clause boundary, which is phrasing, "
            f"and {self.hesitation_pauses} mid-clause, which reads as searching."
        )

    def filler_statement(self) -> str:
        if not self.gaps:
            return "No voiced time went untranscribed — nothing that sounds like an 'um'."
        n = self.filler_count
        if not n:
            return "Voiced gaps were found, but none in the length a filled pause occupies."
        rate = self.filler_per_minute
        return (
            f"{n} filled {'pause' if n == 1 else 'pauses'} — {rate:.1f} a minute — found as "
            "voiced time carrying no word. Counted from the sound, not from the transcript, "
            "which drops most of them."
        )


def analyse(
    words: list[Word],
    speech: list[Span],
    *,
    total_sec: float,
    word_count: int | None = None,
) -> ProsodyReport:
    """The whole Layer 1 acoustic pass. No model, no audio library, no network."""
    return ProsodyReport(
        gaps=voiced_gaps(speech, words),
        pauses=pauses(words),
        fluency=fluency(words, speech, total_sec=total_sec, word_count=word_count),
    )


# Labels for the acoustic measures, kept next to delivery's own map so the two
# sets read as one vocabulary on the page rather than as two systems.
ACOUSTIC_LABELS: dict[str, str] = {
    "filled_pauses": "Filled pauses",
    "articulation": "Articulation",
    "pause_shape": "Pause placement",
}


def metrics(report: ProsodyReport) -> list[DeliveryMetric]:
    """The acoustic pass in the shape Layer 1 already renders.

    Returned as ``DeliveryMetric`` rows so the page needs no second component
    and the operator sees one list of measurements, not "the normal ones" and
    "the audio ones".
    """
    out: list[DeliveryMetric] = []

    rate = report.filler_per_minute
    if rate >= FILLER_PER_MINUTE_HIGH:
        verdict = "off"
    elif rate >= FILLER_PER_MINUTE_HIGH / 2:
        verdict = "watch"
    else:
        # Unlike the transcript count, this one earns "good": it was measured
        # from the sound, so a low number is evidence rather than an absence.
        verdict = "good"
    out.append(
        DeliveryMetric(
            key="filled_pauses",
            label=ACOUSTIC_LABELS["filled_pauses"],
            value=rate,
            unit="per min",
            ideal=f"under {FILLER_PER_MINUTE_HIGH:.0f}",
            verdict=verdict,
            detail=report.filler_statement(),
        )
    )

    f = report.fluency
    gap = f.articulation_rate - f.speaking_rate
    out.append(
        DeliveryMetric(
            key="articulation",
            label=ACOUSTIC_LABELS["articulation"],
            value=f.articulation_rate,
            unit="words/min speaking",
            ideal=f"{WPM_LOW}–{WPM_HIGH}",
            verdict="watch" if gap >= 40 or f.articulation_rate >= WPM_RUSHED else "good",
            detail=f.statement(),
        )
    )

    if report.pauses:
        share = report.hesitation_pauses / len(report.pauses)
        out.append(
            DeliveryMetric(
                key="pause_shape",
                label=ACOUSTIC_LABELS["pause_shape"],
                value=float(report.hesitation_pauses),
                unit="mid-clause",
                ideal="mostly at clause boundaries",
                verdict="off" if share >= 0.75 else "watch" if share >= 0.4 else "good",
                detail=report.pause_statement(),
            )
        )

    return out
