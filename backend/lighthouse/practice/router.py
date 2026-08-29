"""Practice endpoints: the behavioural mock, and the feedback on it.

Nothing here stores audio, and nothing stores the transcript. The browser
captures speech, transcribes it locally, and posts text; the text is analysed,
the analysis is returned, and the text is discarded. What *is* kept is the
measurement -- four numbers, a date and a competency -- because a delivery metric
taken once measures nothing, and watching your own filler rate fall over six
sessions is the entire point of Layer 1. See :mod:`practice.sessions` for the
line between the two.

The three feedback layers arrive together but stay separate in the response,
because they mean different things: delivery is arithmetic, structure is a
convention, and drift is a claim against the corpus.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core import corpus as corpus_service
from ..core import llm
from ..core.config import get_settings
from ..core.db import get_session
from . import audio, delivery, feedback, prosody, questions
from . import sessions as sessions_service

router = APIRouter(prefix="/api/practice", tags=["practice"])


class QuestionOut(BaseModel):
    text: str
    competency: str
    follow_up: str = Field(
        description="Asked after every answer. Real interviewers probe, and this is the "
        "probe people are least ready for — so it is deterministic, not left to a model."
    )


class WordIn(BaseModel):
    text: str
    start: float
    end: float


class SpanIn(BaseModel):
    start: float
    end: float


class AnswerIn(BaseModel):
    transcript: str
    duration_sec: float
    question: str = ""
    competency: str | None = None
    answer_mode: str = Field(
        default=sessions_service.SPOKEN,
        description="'spoken' or 'typed'. Typed answers have no duration, so they are "
        "recorded but never enter a delivery trend — their pace is not the same "
        "measurement as a spoken answer's.",
    )
    words: list[WordIn] = Field(
        default=[],
        description="Word timings when the local transcriber produced them. Without them "
        "the silence measures are absent rather than estimated.",
    )
    speech: list[SpanIn] = Field(
        default=[],
        description="Voiced spans from the local voice-activity detector. Combined with "
        "`words`, the difference between them is where the filled pauses are — a "
        "transcriber drops 'um', so the hole it leaves is the measurement. Without "
        "these the filler count stays a transcript floor rather than a total.",
    )


class MetricOut(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    ideal: str
    verdict: str
    detail: str


class DeliveryOut(BaseModel):
    duration_sec: float
    word_count: int
    is_measurable: bool
    summary: str
    metrics: list[MetricOut] = []
    filler_examples: list[str] = []


class StructureOut(BaseModel):
    part: str
    label: str
    present: bool
    advice: str


class DriftOut(BaseModel):
    claim: str
    detail: str


class TrendOut(BaseModel):
    key: str
    label: str
    first: float
    latest: float
    sessions: int
    change: float
    statement: str


class GapOut(BaseModel):
    start: float
    end: float
    duration: float
    is_probable_filler: bool
    statement: str


class FeedbackOut(BaseModel):
    delivery: DeliveryOut
    structure: list[StructureOut]
    drift: list[DriftOut] = Field(
        default=[],
        description="Figures said aloud that the corpus does not support. The failure "
        "that gets repeated under pressure in a real interview.",
    )
    notes: str
    summary: str
    provider: str
    is_fallback: bool
    trends: list[TrendOut] = Field(
        default=[],
        description="Each delivery metric across the operator's own spoken sessions, "
        "including the one just finished. Empty until there are two to compare.",
    )
    voiced_gaps: list[GapOut] = Field(
        default=[],
        description="Timestamped spans where the voice detector heard sound and the "
        "transcriber wrote no word — where the 'um' was. Present only when the audio "
        "was measured. These are the spans, not a count, so they can be played back.",
    )
    mode: str = Field(
        default="transcript",
        description="'acoustic' when filled pauses were measured from the audio, "
        "'transcript' when only the text was available.",
    )


@router.get("/question", response_model=QuestionOut)
def next_question(
    session: Session = Depends(get_session),
    competency: str | None = None,
    exclude: str | None = None,
) -> QuestionOut:
    """The next question to practise.

    Prefers a competency the story bank does not cover: practising the one you
    already have a polished story for feels good and teaches nothing.
    """
    report = corpus_service.story_coverage(session)
    uncovered = [c.slug for c in report.uncovered]
    chosen = questions.pick(
        uncovered_competencies=uncovered,
        competency=competency,
        exclude=[e for e in (exclude or "").split("|") if e],
    )
    return QuestionOut(
        text=chosen.text, competency=chosen.competency, follow_up=chosen.follow_up
    )


def _review(
    session: Session,
    *,
    transcript: str,
    duration_sec: float,
    words: list[delivery.Word],
    speech: list[prosody.Span],
    question: str,
    competency: str | None,
    answer_mode: str,
) -> FeedbackOut:
    """The whole analysis, shared by the text and the audio routes.

    They differ only in where the transcript and the timings came from -- typed
    in, recognised live by the browser, or transcribed here from a recording --
    and past that point the measurement must be identical, or a trend that spans
    both is comparing two different things.
    """
    facts = corpus_service.list_facts(session)
    sources = [llm.SourceFact(fact_id=f.id, title=f.title, body=f.body or "") for f in facts]

    measured = delivery.analyse(transcript, duration_sec=duration_sec, words=words or None)

    # With both a voice detector and word timings, the filled pauses can be
    # measured from the sound instead of counted out of a transcript that
    # already deleted most of them. The acoustic figure replaces the transcript
    # floor rather than sitting next to it -- two filler numbers on one page,
    # disagreeing, is worse than either alone.
    acoustic = None
    if speech and words and measured.is_measurable:
        # The transcript's word count, not the count of words whisper could
        # place in time -- otherwise the page shows two different totals.
        acoustic = prosody.analyse(
            words, speech, total_sec=duration_sec, word_count=measured.word_count
        )
        measured.metrics = [m for m in measured.metrics if m.key != "filler_density"]
        measured.metrics.extend(prosody.metrics(acoustic))

    reviewed = feedback.build(transcript, sources=sources)

    # Recorded before the trend is read, so the answer just given is the latest
    # point on it rather than missing from its own feedback.
    sessions_service.record(
        session,
        report=measured,
        structure=reviewed.structure,
        drift=reviewed.drift,
        competency=competency,
        question=question,
        answer_mode=answer_mode,
    )
    session.commit()
    tracked = sessions_service.trends(session)

    return FeedbackOut(
        delivery=DeliveryOut(
            duration_sec=measured.duration_sec,
            word_count=measured.word_count,
            is_measurable=measured.is_measurable,
            summary=measured.summary(),
            metrics=[
                MetricOut(
                    key=m.key,
                    label=m.label,
                    value=m.rounded,
                    unit=m.unit,
                    ideal=m.ideal,
                    verdict=m.verdict,
                    detail=m.detail,
                )
                for m in measured.metrics
            ],
            filler_examples=measured.filler_examples,
        ),
        structure=[
            StructureOut(part=s.part, label=s.label, present=s.present, advice=s.advice)
            for s in reviewed.structure
        ],
        drift=[DriftOut(claim=d.claim, detail=d.detail) for d in reviewed.drift],
        notes=reviewed.notes,
        summary=reviewed.summary(),
        provider=reviewed.provider,
        is_fallback=reviewed.is_fallback,
        trends=[
            TrendOut(
                key=t.key,
                label=t.label,
                first=round(t.first, 1),
                latest=round(t.latest, 1),
                sessions=t.sessions,
                change=round(t.change, 1),
                statement=t.statement(),
            )
            for t in tracked
        ],
        voiced_gaps=[
            GapOut(
                start=round(g.start, 2),
                end=round(g.end, 2),
                duration=round(g.duration, 2),
                is_probable_filler=g.is_probable_filler,
                statement=g.statement(),
            )
            for g in (acoustic.gaps if acoustic else [])
        ],
        mode="acoustic" if acoustic else "transcript",
    )


@router.post("/answer", response_model=FeedbackOut)
def review_answer(payload: AnswerIn, session: Session = Depends(get_session)) -> FeedbackOut:
    """Analyse one answer from text, and add its measurements to the record.

    The transcript is analysed and dropped. Only the numbers are kept.
    """
    if not payload.transcript.strip():
        raise HTTPException(status_code=422, detail="Nothing was transcribed.")
    if payload.answer_mode not in (sessions_service.SPOKEN, sessions_service.TYPED):
        raise HTTPException(
            status_code=422,
            detail=f"answer_mode must be 'spoken' or 'typed', got {payload.answer_mode!r}.",
        )

    return _review(
        session,
        transcript=payload.transcript,
        duration_sec=payload.duration_sec,
        words=[delivery.Word(w.text, w.start, w.end) for w in payload.words],
        speech=[prosody.Span(s.start, s.end) for s in payload.speech],
        question=payload.question,
        competency=payload.competency,
        answer_mode=payload.answer_mode,
    )


class CapabilityOut(BaseModel):
    mode: str
    voice_detector: bool
    transcriber: bool
    measures_filled_pauses: bool
    note: str


@router.get("/capabilities", response_model=CapabilityOut)
def capabilities() -> CapabilityOut:
    """What this machine can measure, resolved before the operator records.

    The page asks first and shows the matching control. Letting someone give a
    ninety-second answer and *then* discovering the transcriber is missing is
    the one failure this feature cannot afford, and it is entirely avoidable.
    """
    cap = audio.capability()
    return CapabilityOut(
        mode=cap.mode,
        voice_detector=cap.voice_detector,
        transcriber=cap.transcriber,
        measures_filled_pauses=cap.measures_filled_pauses,
        note=cap.note(),
    )


@router.post("/answer/audio", response_model=FeedbackOut)
async def review_recorded_answer(
    session: Session = Depends(get_session),
    audio_file: UploadFile = File(..., alias="audio"),
    question: str = "",
    competency: str | None = None,
) -> FeedbackOut:
    """Analyse a recording: transcribe it here, detect voice, measure, discard.

    The audio never leaves this machine and is never stored. It is decoded in
    memory; whisper.cpp needs a path, so it gets a temp file that is deleted in
    a ``finally`` whatever happens.
    """
    settings = get_settings()
    payload = await audio_file.read()
    if len(payload) > settings.max_audio_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Recording is {len(payload) // 1_000_000} MB, over the "
                f"{settings.max_audio_bytes // 1_000_000} MB limit. That is roughly eight "
                "minutes; an answer past that has stopped being an answer."
            ),
        )

    cap = audio.capability()
    if not cap.transcriber:
        raise HTTPException(status_code=422, detail=cap.transcriber_reason)

    try:
        decoded = audio.pcm.decode_wav(payload)
    except audio.pcm.AudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    transcript, words = audio.transcribe.transcribe(decoded)
    if not transcript.strip():
        raise HTTPException(
            status_code=422,
            detail="Nothing was transcribed from that recording. Check the microphone level.",
        )

    return _review(
        session,
        transcript=transcript,
        duration_sec=decoded.duration_sec,
        words=words,
        speech=audio.vad.speech_spans(decoded) if cap.voice_detector else [],
        question=question,
        competency=competency,
        answer_mode=sessions_service.SPOKEN,
    )


class SessionOut(BaseModel):
    id: UUID
    occurred_at: datetime
    competency: str | None
    question: str | None
    answer_mode: str
    duration_sec: float | None
    word_count: int
    is_measurable: bool
    metrics: dict[str, float] = {}
    structure_present: list[str] = []
    drift_count: int


class StructureHabitOut(BaseModel):
    part: str
    label: str
    present: int
    total: int
    statement: str


class RecordOut(BaseModel):
    sessions: list[SessionOut]
    trends: list[TrendOut] = []
    structure: list[StructureHabitOut] = Field(
        default=[],
        description="How often each STAR part actually appeared, most-missed first. "
        "A dropped Result is invisible in any single session and obvious across ten.",
    )
    note: str


@router.get("/sessions", response_model=RecordOut)
def practice_record(
    session: Session = Depends(get_session),
    limit: int = Query(default=sessions_service.HISTORY_LIMIT, ge=1, le=200),
) -> RecordOut:
    """The practice record: past sessions, the trend, and the structural habit.

    Measurements only — the answers themselves were never stored.
    """
    rows = sessions_service.history(session, limit=limit)
    tracked = sessions_service.trends(session)
    habits = sessions_service.structure_habits(session, parts=list(feedback.STAR_LABELS))

    spoken = sum(1 for r in rows if r.answer_mode == sessions_service.SPOKEN and r.is_measurable)
    if not rows:
        note = "No sessions yet. Answer one question and this starts filling in."
    elif spoken < 2:
        note = (
            f"{len(rows)} session{'s' if len(rows) != 1 else ''} recorded. "
            "Trends need at least two spoken answers long enough to measure."
        )
    else:
        note = f"{spoken} measurable spoken sessions of {len(rows)} recorded."

    return RecordOut(
        sessions=[
            SessionOut(
                id=r.id,
                occurred_at=r.occurred_at,
                competency=r.competency,
                question=r.question,
                answer_mode=r.answer_mode,
                duration_sec=r.duration_sec,
                word_count=r.word_count,
                is_measurable=r.is_measurable,
                metrics=r.metrics or {},
                structure_present=r.structure_present or [],
                drift_count=r.drift_count,
            )
            for r in reversed(rows)
        ],
        trends=[
            TrendOut(
                key=t.key,
                label=t.label,
                first=round(t.first, 1),
                latest=round(t.latest, 1),
                sessions=t.sessions,
                change=round(t.change, 1),
                statement=t.statement(),
            )
            for t in tracked
        ],
        structure=[
            StructureHabitOut(
                part=h.part,
                label=feedback.STAR_LABELS[h.part],
                present=h.present,
                total=h.total,
                statement=h.statement(),
            )
            for h in habits
        ],
        note=note,
    )


class StoryMatchOut(BaseModel):
    story_id: UUID
    title: str
    competency_tags: list[str]
    is_grounded: bool


@router.get("/question/stories", response_model=list[StoryMatchOut])
def stories_for_competency(
    competency: str, session: Session = Depends(get_session)
) -> list[StoryMatchOut]:
    """The operator's own stories for this competency, if they have any.

    Shown after the answer rather than before it — seeing the story first turns
    a mock into reading practice.
    """
    return [
        StoryMatchOut(
            story_id=s.id,
            title=s.title,
            competency_tags=s.competency_tags or [],
            is_grounded=s.is_grounded,
        )
        for s in corpus_service.list_stories(session)
        if competency in (s.competency_tags or [])
    ]
