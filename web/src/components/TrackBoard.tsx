import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  Application,
  ApplicationEvent,
  Board,
  ResumeVersion,
  Stage,
} from "../api/types";
import { atMidday, today } from "../lib/dates";
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

// What can be logged next comes from the API (`application.next_events`) rather
// than a table here, so the board and the posting window can never drift into
// offering different transitions for the same row.

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

  const log = async (id: string, event: ApplicationEvent, on: string) => {
    setBusyId(id);
    try {
      await api.logEvent(id, { event_type: event, occurred_at: atMidday(on) });
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
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusyId(null);
    }
  };

  const patch = async (
    id: string,
    changes: { notes?: string; resume_version_id?: string; clear_resume_version?: boolean },
  ) => {
    setBusyId(id);
    try {
      await api.patchApplication(id, changes);
      await load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
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

          {board.version_outcomes.some((v) => v.applied > 0) && (
            <section className="card p-4">
              <h2 className="rule-label mb-2">Résumé versions</h2>
              <div className="space-y-1">
                {board.version_outcomes.map((v) => (
                  <p key={v.version_id} className="text-xs text-navy-600">
                    <span className="font-600 text-navy-800">{v.label}</span>
                    <span className="text-navy-400"> — </span>
                    <span className="tabular-nums">{v.statement}</span>
                  </p>
                ))}
              </div>
              <p className="text-2xs text-navy-400 mt-2 leading-relaxed">
                Counts, not rates. A response rate over a handful of applications would move
                twenty points on one reply — compare these once each version has real volume
                behind it.
              </p>
            </section>
          )}

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
                          versions={board.resume_versions}
                          busy={busyId === a.id}
                          onLog={log}
                          onUntrack={untrack}
                          onPatch={patch}
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
                    versions={board.resume_versions}
                    busy={busyId === a.id}
                    onLog={log}
                    onUntrack={untrack}
                    onPatch={patch}
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
  versions,
  busy,
  onLog,
  onUntrack,
  onPatch,
}: {
  application: Application;
  versions: ResumeVersion[];
  busy: boolean;
  onLog: (id: string, event: ApplicationEvent, on: string) => void;
  onUntrack: (id: string) => void;
  onPatch: (
    id: string,
    changes: { notes?: string; resume_version_id?: string; clear_resume_version?: boolean },
  ) => void;
}) {
  const [open, setOpen] = useState(false);
  // Stage buttons log against this date, not against "now". Back-filling a
  // search that already happened is the normal first use of this board, and
  // stamping it all with today would make every wait-time figure downstream
  // wrong -- which is most of what the funnel is for.
  const [on, setOn] = useState(today());
  const next = application.next_events;

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
          {/* Which résumé went out. Without it the funnel can only say how the
              pile did, not whether the rewrite changed anything. */}
          {versions.length > 0 && (
            <li className="pt-1">
              <select
                value={application.resume_version_id ?? ""}
                disabled={busy}
                onChange={(e) =>
                  onPatch(
                    application.id,
                    e.target.value
                      ? { resume_version_id: e.target.value }
                      : { clear_resume_version: true },
                  )
                }
                className="text-2xs bg-white border border-navy-200 rounded px-1.5 py-0.5 w-full
                           text-navy-700 hover:border-navy-300 focus:border-beacon-500 outline-none"
              >
                <option value="">résumé not recorded</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </li>
          )}
          <li className="pt-1">
            <NotesField
              value={application.notes ?? ""}
              disabled={busy}
              onCommit={(notes) => onPatch(application.id, { notes })}
            />
          </li>
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
        <div className="mt-2.5 pt-2 border-t border-navy-100 space-y-1.5">
          <div className="flex items-center gap-1.5">
            <label className="text-2xs text-navy-400 shrink-0">on</label>
            <input
              type="date"
              value={on}
              max={today()}
              onChange={(e) => setOn(e.target.value || today())}
              title="When this actually happened. Defaults to today; change it when logging something from last week."
              className="text-2xs bg-white border border-navy-200 rounded px-1.5 py-0.5
                         text-navy-700 hover:border-navy-300 focus:border-beacon-500 outline-none"
            />
            {on !== today() && <span className="text-2xs text-beacon-700">back-dated</span>}
          </div>
          <div className="flex flex-wrap gap-1">
          {next.map((n) => (
            <button
              key={n.event_type}
              onClick={() => onLog(application.id, n.event_type, on)}
              disabled={busy}
              className={`text-2xs px-1.5 py-0.5 rounded transition-colors disabled:opacity-40 ${
                n.is_setback
                  ? "text-navy-400 hover:text-bad hover:bg-bad/5"
                  : "text-navy-600 hover:text-beacon-700 hover:bg-beacon-glow"
              }`}
            >
              {n.label}
            </button>
          ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Commits on blur rather than per keystroke: every save refetches the board. */
function NotesField({
  value,
  disabled,
  onCommit,
}: {
  value: string;
  disabled: boolean;
  onCommit: (value: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <textarea
      value={draft}
      disabled={disabled}
      rows={2}
      placeholder="Notes — who referred you, what they said, anything you'd forget"
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => draft !== value && onCommit(draft)}
      className="text-2xs bg-white border border-navy-200 rounded px-1.5 py-1 w-full resize-y
                 text-navy-700 placeholder:text-navy-300 hover:border-navy-300
                 focus:border-beacon-500 outline-none"
    />
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
