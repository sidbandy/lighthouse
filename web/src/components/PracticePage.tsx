import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AnswerFeedback, PracticeQuestion, StoryMatch } from "../api/types";

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

  useEffect(() => {
    if (phase !== "listening") return;
    const timer = setInterval(() => setElapsed((Date.now() - startedAt.current) / 1000), 250);
    return () => clearInterval(timer);
  }, [phase]);

  const start = () => {
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

    if (!full) {
      setPhase("idle");
      setError("Nothing was transcribed. Check the mic, or type the answer instead.");
      return;
    }

    setPhase("reviewing");
    try {
      const result = await api.reviewAnswer({
        transcript: full,
        duration_sec: duration,
        question: question?.text,
        competency: question?.competency,
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
            {phase === "reviewing" && <span className="text-xs text-navy-500">Reading it…</span>}
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
        <FeedbackPanel feedback={feedback} stories={stories} wasSpoken={wasSpoken} />
      )}
    </div>
  );
}

function FeedbackPanel({
  feedback,
  stories,
  wasSpoken,
}: {
  feedback: AnswerFeedback;
  stories: StoryMatch[];
  wasSpoken: boolean;
}) {
  const verdictColor: Record<string, string> = {
    good: "text-good",
    watch: "text-warn",
    off: "text-bad",
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
            {feedback.delivery.filler_examples.length > 0 && (
              <p className="text-2xs text-navy-400 pt-1">
                Fillers: {feedback.delivery.filler_examples.join(", ")}
              </p>
            )}
          </div>
        )}
      </section>

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
