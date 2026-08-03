import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Application, ApplicationEvent, Board, Stage } from "../api/types";
import { FunnelPanel } from "./FunnelPanel";

// The application board: everything you've applied to, what stage it's at, and
// how long it's been quiet.
//
// The board groups by stage rather than showing a kanban of draggable cards.
// Dragging implies you choose the stage; you don't — the employer does, and what
// you're actually doing is recording something that already happened on a date.
// So the interaction is "log what happened", and the grouping follows.

const COLUMNS: { stage: Stage; title: string; blurb: string; rule: string }[] = [
  {
    stage: "SAVED",
    title: "Saved",
    blurb: "Worth applying to. Nothing sent yet.",
    rule: "bg-navy-300",
  },
  {
    stage: "APPLIED",
    title: "Applied",
    blurb: "Sent, waiting to hear back.",
    rule: "bg-beacon-500",
  },
  {
    stage: "ASSESSMENT",
    title: "Assessment",
    blurb: "An OA or take-home is in play.",
    rule: "bg-safety",
  },
  {
    stage: "INTERVIEW",
    title: "Interviewing",
    blurb: "Scheduled or done, awaiting the next step.",
    rule: "bg-target",
  },
];

// What you can log next, given where an application is. Keeping this as data
// means the board never offers a transition that reads as nonsense — you cannot
// log an offer on something you never applied to.
const NEXT_EVENTS: Record<Stage, { event: ApplicationEvent; label: string }[]> = {
  SAVED: [
    { event: "applied", label: "Applied" },
    { event: "withdrawn", label: "Not applying" },
  ],
  APPLIED: [
    { event: "assessment_received", label: "Got an OA" },
    { event: "interview_scheduled", label: "Interview booked" },
    { event: "rejected", label: "Rejected" },
    { event: "withdrawn", label: "Withdrew" },
  ],
  ASSESSMENT: [
    { event: "assessment_completed", label: "OA done" },
    { event: "interview_scheduled", label: "Interview booked" },
    { event: "rejected", label: "Rejected" },
  ],
  INTERVIEW: [
    { event: "interview_completed", label: "Interview done" },
    { event: "final_round", label: "Final round" },
    { event: "offer", label: "Offer" },
    { event: "rejected", label: "Rejected" },
  ],
  FINAL: [
    { event: "offer", label: "Offer" },
    { event: "rejected", label: "Rejected" },
  ],
  OFFER: [
    { event: "accepted", label: "Accepted" },
    { event: "rejected", label: "Declined" },
  ],
  REJECTED: [],
  WITHDRAWN: [],
  ACCEPTED: [],
};

export function TrackBoard() {
  const [board, setBoard] = useState<Board | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showClosed, setShowClosed] = useState(false);

  const load = useCallback(async () => {
    try {
      setBoard(await api.board());
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }, []);

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, [load]);

  const log = async (id: string, event: ApplicationEvent) => {
    setBusyId(id);
    try {
      await api.logEvent(id, { event_type: event });
      await load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusyId(null);
    }
  };

  const untrack = async (id: string) => {
    setBusyId(id);
    try {
      await api.untrack(id);
      await load();
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <CenteredNote>Loading your board…</CenteredNote>;
  if (error && !board)
    return (
      <CenteredNote>
        <p className="text-bad">Could not reach the API.</p>
        <p className="text-2xs text-navy-400 mt-1">Is the backend running on :8077?</p>
      </CenteredNote>
    );
  if (!board) return null;

  const closed = board.applications.filter((a) => a.is_terminal);
  const live = board.applications.filter((a) => !a.is_terminal);

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-lg font-700 text-navy-900">Your applications</h1>
          <p className="text-sm text-navy-500 mt-1 max-w-2xl">
            What you sent, where it got to, and how long it's been quiet. Every stage is a dated
            fact you logged — nothing here is inferred, and nothing predicts your odds.
          </p>
        </div>
        {closed.length > 0 && (
          <button onClick={() => setShowClosed((v) => !v)} className="btn-toggle text-xs shrink-0">
            {showClosed ? "Hide" : "Show"} {closed.length} closed
          </button>
        )}
      </div>

      {error && <div className="card p-2.5 border-bad/30 bg-bad/5 text-xs text-bad">{error}</div>}

      {board.applications.length === 0 ? (
        <EmptyBoard />
      ) : (
        <>
          <FunnelPanel funnel={board.funnel} />

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {COLUMNS.map((col) => {
              const items = live.filter((a) => a.stage === col.stage);
              return (
                <section key={col.stage} className="flex flex-col min-w-0">
                  <header className="mb-2.5">
                    <div className={`h-0.5 w-full rounded-full ${col.rule}`} />
                    <div className="flex items-baseline gap-2 mt-2">
                      <h2 className="text-sm font-700 text-navy-800">{col.title}</h2>
                      <span className="text-2xs text-navy-400 tabular-nums">{items.length}</span>
                    </div>
                    <p className="text-2xs text-navy-400 leading-snug mt-0.5">{col.blurb}</p>
                  </header>
                  <div className="flex flex-col gap-2">
                    {items.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-navy-200 p-3 text-2xs text-navy-400">
                        Nothing here.
                      </div>
                    ) : (
                      items.map((a) => (
                        <ApplicationCard
                          key={a.id}
                          application={a}
                          busy={busyId === a.id}
                          onLog={log}
                          onUntrack={untrack}
                        />
                      ))
                    )}
                  </div>
                </section>
              );
            })}
          </div>

          {showClosed && closed.length > 0 && (
            <section>
              <h2 className="rule-label mb-2">Closed</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2">
                {closed.map((a) => (
                  <ApplicationCard
                    key={a.id}
                    application={a}
                    busy={busyId === a.id}
                    onLog={log}
                    onUntrack={untrack}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function ApplicationCard({
  application,
  busy,
  onLog,
  onUntrack,
}: {
  application: Application;
  busy: boolean;
  onLog: (id: string, event: ApplicationEvent) => void;
  onUntrack: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const next = NEXT_EVENTS[application.stage];

  return (
    <div className={`card p-3 ${application.is_terminal ? "opacity-60" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <a
            href={application.posting_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-600 text-navy-900 hover:text-beacon-700 transition-colors line-clamp-2"
          >
            {application.posting_title}
          </a>
          <div className="text-2xs text-navy-500 truncate mt-0.5">{application.company_name}</div>
        </div>
        <button
          onClick={() => setOpen((v) => !v)}
          className="btn-ghost text-2xs px-1.5 py-0.5 shrink-0"
          title="History"
        >
          {open ? "−" : "⋯"}
        </button>
      </div>

      {/* The ghosting feature, in full: a subtraction between two real dates. */}
      {application.silence_note && (
        <p
          className={`mt-2 text-2xs ${
            (application.days_silent ?? 0) >= 30 ? "text-beacon-700 font-600" : "text-navy-500"
          }`}
        >
          {application.silence_note}
        </p>
      )}

      {open && (
        <ol className="mt-2 pt-2 border-t border-navy-100 space-y-1">
          {application.timeline.map((entry, i) => (
            <li key={i} className="text-2xs text-navy-500 flex gap-2">
              <span className="tabular-nums text-navy-400 shrink-0">
                {entry.occurred_at.slice(0, 10)}
              </span>
              <span className="text-navy-700">{entry.label}</span>
              {entry.note && <span className="text-navy-400 italic truncate">{entry.note}</span>}
            </li>
          ))}
          <li>
            <button
              onClick={() => onUntrack(application.id)}
              disabled={busy}
              className="text-2xs text-navy-400 hover:text-bad transition-colors mt-1"
            >
              Remove from board
            </button>
          </li>
        </ol>
      )}

      {next.length > 0 && (
        <div className="mt-2.5 pt-2 border-t border-navy-100 flex flex-wrap gap-1">
          {next.map((n) => (
            <button
              key={n.event}
              onClick={() => onLog(application.id, n.event)}
              disabled={busy}
              className={`text-2xs px-1.5 py-0.5 rounded transition-colors disabled:opacity-40 ${
                n.event === "rejected" || n.event === "withdrawn"
                  ? "text-navy-400 hover:text-bad hover:bg-bad/5"
                  : "text-navy-600 hover:text-beacon-700 hover:bg-beacon-glow"
              }`}
            >
              {n.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function EmptyBoard() {
  return (
    <div className="rounded-xl border border-dashed border-navy-200 p-10 text-center">
      <p className="text-sm text-navy-700">Nothing tracked yet.</p>
      <p className="text-2xs text-navy-400 mt-1 max-w-md mx-auto leading-relaxed">
        Open a posting from Discover and save it here. Once a few are logged, this page can tell
        you how long each company actually takes to reply — from your own dates, not from averages
        someone else published.
      </p>
    </div>
  );
}

function CenteredNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center text-sm text-navy-600 py-24">
      {children}
    </div>
  );
}
