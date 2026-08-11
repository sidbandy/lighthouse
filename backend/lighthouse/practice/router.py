"""Practice endpoints: the behavioural mock, and the feedback on it.

Nothing here stores audio. The browser captures speech, transcribes it locally,
and posts text; the transcript is analysed and the analysis is returned. A
recording of the operator rehearsing is not something this project needs to keep.

The three feedback layers arrive together but stay separate in the response,
because they mean different things: delivery is arithmetic, structure is a
convention, and drift is a claim against the corpus.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core import corpus as corpus_service
from ..core import llm
from ..core.db import get_session
from . import delivery, feedback, questions

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


class AnswerIn(BaseModel):
    transcript: str
    duration_sec: float
    question: str = ""
    competency: str | None = None
    words: list[WordIn] = Field(
        default=[],
        description="Word timings when the local transcriber produced them. Without them "
        "the silence measures are absent rather than estimated.",
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


@router.post("/answer", response_model=FeedbackOut)
def review_answer(payload: AnswerIn, session: Session = Depends(get_session)) -> FeedbackOut:
    """Analyse one spoken answer. Nothing is stored.

    Layer 1 is computed here with no model at all, so it works offline and is
    identical every time — which is what makes a trend across sessions mean
    something.
    """
    if not payload.transcript.strip():
        raise HTTPException(status_code=422, detail="Nothing was transcribed.")

    facts = corpus_service.list_facts(session)
    sources = [
        llm.SourceFact(fact_id=f.id, title=f.title, body=f.body or "") for f in facts
    ]

    measured = delivery.analyse(
        payload.transcript,
        duration_sec=payload.duration_sec,
        words=[delivery.Word(w.text, w.start, w.end) for w in payload.words] or None,
    )
    reviewed = feedback.build(payload.transcript, sources=sources)

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
