import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { AnswerRecorder, canRecord } from "../lib/recorder";
import type {
  AnswerFeedback,
  PracticeCapability,
  PracticeQuestion,
  StoryMatch,
} from "../api/types";

// Behavioural practice: say the answer out loud, then read what actually
// happened.
//
// Everything about the voice loop is local. The browser's own speech engine
// does recognition and the interviewer's voice, so no audio leaves the machine
// and nothing is stored — not the recording, not the transcript. The only thing
// posted is text, and only when you press stop.
//
// The feedback is deliberately three separate things, because they fail
// separately. Delivery is arithmetic over the transcript and never involves a
// model. Structure is a convention about STAR answers. Drift compares figures
// you said against your corpus, which is the one that catches "led a team of
// five" when the corpus says three — the mistake you would otherwise repeat in
// a real room.

type Phase = "idle" | "listening" | "reviewing" | "done";

// The browser speech API is not in TypeScript's DOM lib. Narrow shims rather
// than `any`, so the call sites still typecheck.
interface SpeechResultAlternative {
  transcript: string;
}
interface SpeechResult {
  0: SpeechResultAlternative;
  isFinal: boolean;
  length: number;
}
interface SpeechEvent {
  resultIndex: number;
  results: { length: number; [i: number]: SpeechResult };
}
interface Recognizer {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((e: SpeechEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

function createRecognizer(): Recognizer | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => Recognizer;
    webkitSpeechRecognition?: new () => Recognizer;
  };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor) return null;
  const r = new Ctor();
  r.continuous = true;
  r.interimResults = true;
  r.lang = "en-US";
  return r;
}

function speak(text: string) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.98;
  window.speechSynthesis.speak(utterance);
}

export function PracticePage() {
  const [question, setQuestion] = useState<PracticeQuestion | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [transcript, setTranscript] = useState("");
  const [interim, setInterim] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [cap, setCap] = useState<PracticeCapability | null>(null);
  const [measuring, setMeasuring] = useState(false);
  const recorder = useRef<AnswerRecorder | null>(null);
  const [feedback, setFeedback] = useState<AnswerFeedback | null>(null);
  const [stories, setStories] = useState<StoryMatch[]>([]);
  const [asked, setAsked] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [followUpShown, setFollowUpShown] = useState(false);
  // Delivery metrics only mean something for speech.
  const [wasSpoken, setWasSpoken] = useState(true);

  const recognizer = useRef<Recognizer | null>(null);
  const startedAt = useRef<number>(0);
  const supported = useRef<boolean>(typeof window !== "undefined" && !!createRecognizer());

  const nextQuestion = useCallback(async () => {
    try {
      const q = await api.practiceQuestion(undefined, asked);
      setQuestion(q);
      setTranscript("");
      setInterim("");
      setFeedback(null);
      setStories([]);
      setElapsed(0);
      setFollowUpShown(false);
      setPhase("idle");
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }, [asked]);

  useEffect(() => {
    nextQuestion();
    // Only on mount: `asked` changing must not pull a new question mid-session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Asked before the operator records, never after. Discovering that a
  // ninety-second answer could not be measured once it is over is the one
  // failure this feature cannot afford.
  useEffect(() => {
    api.practiceCapabilities().then(setCap).catch(() => setCap(null));
  }, []);

  useEffect(() => {
    if (phase !== "listening") return;
    const timer = setInterval(() => setElapsed((Date.now() - startedAt.current) / 1000), 250);
    return () => clearInterval(timer);
  }, [phase]);

  const start = async () => {
    const r = createRecognizer();
    if (!r) {
      setError(
        "This browser has no speech recognition. Chrome and Edge have it; Firefox does not. " +
          "You can still type the answer below and get the same feedback.",
      );
      return;
    }
    recognizer.current = r;
    setTranscript("");
    setInterim("");
    startedAt.current = Date.now();
    setWasSpoken(true);

    r.onresult = (e) => {
      let final = "";
      let pending = "";
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        const result = e.results[i];
        if (result.isFinal) final += result[0].transcript + " ";
        else pending += result[0].transcript;
      }
      if (final) setTranscript((t) => t + final);
      setInterim(pending);
    };
    r.onerror = (e) => {
      if (e.error !== "no-speech" && e.error !== "aborted") {
        setError(`Speech recognition stopped: ${e.error}`);
      }
    };
    r.onend = () => {
      // Chrome ends the stream on a long pause. Restart it so a thinking pause
      // does not silently end the answer mid-sentence.
      if (recognizer.current === r) {
        try {
          r.start();
        } catch {
          /* already restarted */
        }
      }
    };

    // Web Speech drives the live captions; the recording is what gets
    // measured. Two transcripts of one answer, which is the point: the operator
    // watches the fast one while the accurate one is being made.
    if (cap?.measures_filled_pauses && canRecord()) {
      try {
        recorder.current = await AnswerRecorder.start();
      } catch {
        // Microphone denied or busy. The answer still works from speech
        // recognition alone, so this is a downgrade rather than a failure.
        recorder.current = null;
      }
    }

    r.start();
    setPhase("listening");
    setError(null);
  };

  const stop = async () => {
    const r = recognizer.current;
    recognizer.current = null;
    r?.stop();

    const duration = (Date.now() - startedAt.current) / 1000;
    const full = (transcript + " " + interim).trim();
    setInterim("");
    setElapsed(duration);

    const rec = recorder.current;
    recorder.current = null;

    if (!full && !rec) {
      setPhase("idle");
      setError("Nothing was transcribed. Check the mic, or type the answer instead.");
      return;
    }

    setPhase("reviewing");
    try {
      let result: AnswerFeedback | null = null;

      if (rec) {
        // The measured path. If anything in it fails — microphone, decoding,
        // the transcriber — fall through to the live transcript below rather
        // than losing the answer. Someone who has just spoken for ninety
        // seconds should never be told to do it again.
        try {
          setMeasuring(true);
          const { wav } = await rec.stop();
          result = await api.reviewRecordedAnswer(wav, {
            question: question?.text,
            competency: question?.competency,
          });
        } catch {
          result = null;
        } finally {
          setMeasuring(false);
        }
      }

      if (!result) {
        if (!full) {
          setPhase("idle");
          setError("Nothing was transcribed. Check the mic, or type the answer instead.");
          return;
        }
        result = await api.reviewAnswer({
          transcript: full,
          duration_sec: duration,
          question: question?.text,
          competency: question?.competency,
          answer_mode: "spoken",
        });
      }

      setFeedback(result);
      if (question) {
        setStories(await api.storiesFor(question.competency).catch(() => []));
        setAsked((a) => [...a, question.text]);
      }
      setPhase("done");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setPhase("idle");
    }
  };

  // A typed answer has no duration, so the delivery layer has nothing to
  // measure. Saying "too short to measure" would read as "you spoke too
  // briefly", which is a judgement about something that never happened.
  const submitTyped = async () => {
    if (!transcript.trim()) return;
    setWasSpoken(false);
    setPhase("reviewing");
    try {
      const result = await api.reviewAnswer({
        transcript: transcript.trim(),
        duration_sec: 0,
        question: question?.text,
        competency: question?.competency,
        answer_mode: "typed",
      });
      setFeedback(result);
      if (question) {
        setStories(await api.storiesFor(question.competency).catch(() => []));
        setAsked((a) => [...a, question.text]);
      }
      setPhase("done");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setPhase("idle");
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-6 space-y-5">
      <div>
        <h1 className="text-lg font-700 text-navy-900">Behavioural practice</h1>
        <p className="text-sm text-navy-500 mt-1 leading-relaxed">
          Say the answer out loud, then read what actually happened. Everything runs in your
          browser — no audio leaves this machine, and nothing is recorded or stored.
          {cap?.measures_filled_pauses && (
            <>
              {" "}
              Filled pauses are measured from the sound by a transcriber running on this
              machine; the recording is deleted the moment it has been read.
            </>
          )}
        </p>
      </div>

      {error && (
        <div className="card p-3 border-warn/30 bg-warn/5 text-xs text-navy-700 leading-relaxed">
          {error}
        </div>
      )}

      {question && (
        <section className="card p-5 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-2xs uppercase tracking-wide text-navy-400">
                {question.competency}
              </p>
              <p className="text-base text-navy-900 mt-1 leading-snug">{question.text}</p>
            </div>
            <button
              onClick={() => speak(question.text)}
              className="btn-ghost text-2xs shrink-0"
              title="Hear it — answering a voice is closer to the real thing than reading"
            >
              ▸ Read aloud
            </button>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {phase === "idle" && (
              <button onClick={start} className="btn-primary text-xs" disabled={!supported.current}>
                Start answering
              </button>
            )}
            {phase === "listening" && (
              <>
                <button onClick={stop} className="btn-primary text-xs">
                  Stop
                </button>
                <span className="text-2xs text-beacon-700 tabular-nums">
                  ● {Math.round(elapsed)}s
                </span>
              </>
            )}
            {phase === "reviewing" && (
              <span className="text-xs text-navy-500">
                {measuring
                  ? "Transcribing on this machine — a few seconds…"
                  : "Reading it…"}
              </span>
            )}
            {phase === "done" && (
              <button onClick={nextQuestion} className="btn-primary text-xs">
                Next question
              </button>
            )}
            {!supported.current && phase === "idle" && (
              <span className="text-2xs text-navy-400">
                No speech recognition in this browser — type below instead.
              </span>
            )}
          </div>

          {(phase === "listening" || phase === "idle") && (
            <div>
              <textarea
                value={transcript + (interim ? ` ${interim}` : "")}
                onChange={(e) => setTranscript(e.target.value)}
                rows={5}
                placeholder="Live captions appear here as you speak. You can also type an answer and get the same feedback."
                className="field text-xs resize-y leading-relaxed"
              />
              {phase === "idle" && transcript.trim() && (
                <button onClick={submitTyped} className="btn-toggle text-xs mt-2">
                  Review what I typed
                </button>
              )}
            </div>
          )}
        </section>
      )}

      {phase === "done" && question && !followUpShown && (
        <section className="card p-4 border-beacon-500/30 bg-beacon-glow">
          <p className="text-2xs uppercase tracking-wide text-navy-500">The follow-up</p>
          <p className="text-sm text-navy-900 mt-1">{question.follow_up}</p>
          <p className="text-2xs text-navy-500 mt-1.5 leading-relaxed">
            Asked after almost every behavioural answer, and the one people are least ready
            for. Answer it out loud before you move on.
          </p>
          <button onClick={() => setFollowUpShown(true)} className="btn-toggle text-xs mt-2">
            Done
          </button>
        </section>
      )}

      {feedback && (
        <FeedbackPanel
          feedback={feedback}
          stories={stories}
          wasSpoken={wasSpoken}
          cap={cap}
        />
      )}
    </div>
  );
}

function FeedbackPanel({
  feedback,
  stories,
  wasSpoken,
  cap,
}: {
  feedback: AnswerFeedback;
  stories: StoryMatch[];
  wasSpoken: boolean;
  cap: PracticeCapability | null;
}) {
  const verdictColor: Record<string, string> = {
    good: "text-good",
    watch: "text-warn",
    off: "text-bad",
    // Measured, but not judgeable — a filler count taken from a transcript is a
    // floor, since every transcriber drops "um". Rendered in the quietest tier
    // so it reads as "no verdict" rather than as a pass.
    unknown: "text-navy-400",
  };

  return (
    <div className="space-y-4">
      {/* Drift leads when there is any: a wrong number repeated in a real
          interview is a worse problem than a missing Result. */}
      {feedback.drift.length > 0 && (
        <section className="card p-4 border-bad/30 bg-bad/5">
          <h2 className="rule-label mb-2">
            <span className="text-bad">Claims your corpus does not back</span>
          </h2>
          {feedback.drift.map((d) => (
            <p key={d.claim} className="text-xs text-navy-700 leading-relaxed">
              {d.detail}
            </p>
          ))}
        </section>
      )}

      <section className="card p-4">
        <h2 className="rule-label mb-2">Delivery</h2>
        <p className="text-2xs text-navy-500 mb-2">
          {wasSpoken
            ? feedback.delivery.summary
            : "Not measured — pace, fillers and pauses only exist in speech. Use the mic to get this half."}
        </p>
        {wasSpoken && feedback.delivery.is_measurable && (
          <div className="space-y-1.5">
            {feedback.delivery.metrics.map((m) => (
              <div key={m.key} className="flex items-baseline gap-2 text-xs flex-wrap">
                <span className="text-navy-700 w-24 shrink-0">{m.label}</span>
                <span className={`tabular-nums font-600 ${verdictColor[m.verdict]}`}>
                  {m.value}
                </span>
                <span className="text-2xs text-navy-400">
                  {m.unit} · ideal {m.ideal}
                </span>
                <span className="text-2xs text-navy-500 basis-full sm:basis-auto sm:ml-2">
                  {m.detail}
                </span>
              </div>
            ))}
            {/* Where the "um" was, as spans rather than a total. A count is a
                number to argue with; a timestamp is something to go and hear.
                Only the ones in the filled-pause band are called fillers — a
                longer voiced stretch is shown and left unnamed, because the
                detector cannot tell a laugh from a word it missed. */}
            {feedback.voiced_gaps.length > 0 && (
              <div className="pt-2 mt-1 border-t border-navy-100">
                <p className="text-2xs text-navy-400 mb-1">
                  Voiced time carrying no word — play these back to hear what they were:
                </p>
                <ul className="space-y-0.5">
                  {feedback.voiced_gaps.slice(0, 6).map((g) => (
                    <li key={`${g.start}-${g.end}`} className="text-2xs text-navy-600">
                      <span className="tabular-nums text-navy-500">{g.statement}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {feedback.mode === "transcript" && cap && !cap.measures_filled_pauses && (
              <p className="text-2xs text-navy-400 pt-2 mt-1 border-t border-navy-100 leading-relaxed">
                {cap.note}
              </p>
            )}
            {feedback.delivery.filler_examples.length > 0 && (
              <p className="text-2xs text-navy-400 pt-1">
                Fillers that survived the transcript:{" "}
                {feedback.delivery.filler_examples.join(", ")}
              </p>
            )}
          </div>
        )}
      </section>

      {/* Only for spoken, measurable answers: a typed answer has no pace to
          compare, and a four-word one has nothing to compare either. The
          numbers are shown without a colour, because direction is not the same
          as improvement — filler density falling is good, pace falling may not
          be, and the reader is the one who knows which they were aiming at. */}
      {wasSpoken && feedback.delivery.is_measurable && (
        <section className="card p-4">
          <h2 className="rule-label mb-2">Against your own sessions</h2>
          {feedback.trends.length === 0 ? (
            <p className="text-2xs text-navy-500 leading-relaxed">
              This is the first answer Lighthouse has measured. Do one more and it can
              show you whether your delivery is moving — the only baseline worth
              anything here is you, earlier.
            </p>
          ) : (
            <div className="space-y-1.5">
              {feedback.trends.map((t) => (
                <div key={t.key} className="flex items-baseline gap-2 text-xs flex-wrap">
                  <span className="text-navy-700 w-24 shrink-0">{t.label}</span>
                  <span className="tabular-nums text-navy-500">
                    {t.first} <span className="text-navy-300">→</span>{" "}
                    <span className="font-600 text-navy-900">{t.latest}</span>
                  </span>
                  <span className="text-2xs text-navy-500 basis-full sm:basis-auto sm:ml-2">
                    {t.statement}
                  </span>
                </div>
              ))}
              <p className="text-2xs text-navy-400 pt-1">
                Measurements only — nothing you said was stored.
              </p>
            </div>
          )}
        </section>
      )}

      <section className="card p-4">
        <h2 className="rule-label mb-2">Structure</h2>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mb-2">
          {feedback.structure.map((s) => (
            <span
              key={s.part}
              className={`term ${s.present ? "border-good text-navy-600" : "border-beacon-500 text-navy-700"}`}
              title={s.advice}
            >
              {s.label}
            </span>
          ))}
        </div>
        {feedback.structure
          .filter((s) => !s.present)
          .map((s) => (
            <p key={s.part} className="text-2xs text-navy-600 leading-relaxed">
              <span className="text-navy-400">{s.label}: </span>
              {s.advice}
            </p>
          ))}
      </section>

      <section className="card p-4">
        <h2 className="rule-label mb-2">What to change</h2>
        <p className="text-xs text-navy-700 leading-relaxed">{feedback.notes}</p>
        <p className="text-2xs text-navy-400 mt-2">
          {feedback.is_fallback || feedback.provider === "rule_based"
            ? "Written from rules, not a model — works offline and says the same thing every time."
            : `Reviewed by ${feedback.provider}.`}{" "}
          Feedback only ever refers to what you actually said.
        </p>
      </section>

      {stories.length > 0 && (
        <section className="card p-4">
          <h2 className="rule-label mb-2">Your stories for this competency</h2>
          <ul className="space-y-1">
            {stories.map((s) => (
              <li key={s.story_id} className="text-xs text-navy-700">
                {s.title}
                {!s.is_grounded && (
                  <span className="text-2xs text-warn ml-2">not tied to a corpus fact</span>
                )}
              </li>
            ))}
          </ul>
          <p className="text-2xs text-navy-400 mt-2">
            Shown after the answer on purpose — reading one first turns a mock into recitation.
          </p>
        </section>
      )}
    </div>
  );
}
