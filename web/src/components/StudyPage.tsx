import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { AttemptOutcome, StudyHome, Suggestion, TopicNeed } from "../api/types";

// Everything to study, in one place, ordered by what your own search says.
//
// Four blocks, and the order is the argument. Reviews first because they are
// finite and expire. Then what to attempt next, at your actual level. Then what
// your *applications* say you should be learning besides algorithms — the part
// no generic list can give you. The full pattern record sits last: it is
// reference, not a to-do.
//
// Nothing here is a score. "0 of 3 clean, last 4 days ago" tells you what to do
// next; "graph mastery 0.34" invites you to trust a number fitted to three
// data points.

const OUTCOMES: { value: AttemptOutcome; label: string; hint: string }[] = [
  { value: "solved_clean", label: "Clean", hint: "No hints, in reasonable time" },
  { value: "solved_with_hint", label: "Needed a hint", hint: "Got there with help" },
  { value: "solved_over_time", label: "Over time", hint: "Solved, but slowly" },
  { value: "failed", label: "Didn't get it", hint: "Resets the review interval" },
];

const DIFFICULTY_COLOR: Record<string, string> = {
  easy: "text-good",
  medium: "text-warn",
  hard: "text-bad",
};

export function StudyPage() {
  const [home, setHome] = useState<StudyHome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    try {
      setHome(await api.study());
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const log = async (slug: string, outcome: AttemptOutcome) => {
    setBusy(slug);
    try {
      setHome(await api.logAttempt({ problem_slug: slug, outcome }));
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  if (error && !home)
    return (
      <CenteredNote>
        <p className="text-bad">Could not reach the API.</p>
        <p className="text-2xs text-navy-400 mt-1">Is the backend running on :8077?</p>
      </CenteredNote>
    );
  if (!home) return <CenteredNote>Loading your study plan…</CenteredNote>;

  const visiblePatterns = showAll ? home.patterns : home.patterns.slice(0, 6);

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-5">
      <div>
        <h1 className="text-lg font-700 text-navy-900">Study</h1>
        <p className="text-sm text-navy-500 mt-1 max-w-2xl leading-relaxed">
          What to practise, what is due for review, and what the jobs you actually applied to
          say you should be learning. Everything here is counted from your own record — there
          are no scores on this page.
        </p>
      </div>

      {error && <div className="card p-2.5 border-bad/30 bg-bad/5 text-xs text-bad">{error}</div>}

      {home.prerequisite_gaps.map((gap) => (
        <div key={gap} className="card p-3 border-warn/30 bg-warn/5 text-xs text-navy-700">
          {gap}
        </div>
      ))}

      {/* Finite and expiring, so it goes first. */}
      <section className="card p-4">
        <h2 className="rule-label mb-2">Due for review</h2>
        <p className="text-2xs text-navy-500 mb-2 leading-relaxed">{home.reviews.note}</p>
        {home.reviews.due.length > 0 && (
          <ul className="space-y-1.5">
            {home.reviews.due.map((r) => (
              <li key={r.problem_slug} className="flex items-baseline gap-2 text-xs flex-wrap">
                <a
                  href={r.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-600 text-navy-900 hover:text-beacon-700 transition-colors"
                >
                  {r.title}
                </a>
                <span className="text-2xs text-navy-400">{r.statement}</span>
                <span className="ml-auto flex gap-1">
                  {OUTCOMES.map((o) => (
                    <button
                      key={o.value}
                      title={o.hint}
                      disabled={busy === r.problem_slug}
                      onClick={() => log(r.problem_slug, o.value)}
                      className="text-2xs px-1.5 py-0.5 rounded text-navy-600 hover:text-beacon-700
                                 hover:bg-beacon-glow transition-colors disabled:opacity-40"
                    >
                      {o.label}
                    </button>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* New work, entered at the level the record implies. */}
      <section className="card p-4">
        <h2 className="rule-label mb-2">Practise next</h2>
        {home.suggestions.length === 0 ? (
          <p className="text-xs text-navy-400">
            Nothing left in the catalogue for these patterns — you have solved them all clean.
          </p>
        ) : (
          <div className="space-y-2">
            {home.suggestions.map((s) => (
              <SuggestionRow
                key={s.problem.slug}
                suggestion={s}
                busy={busy === s.problem.slug}
                onLog={log}
              />
            ))}
          </div>
        )}
      </section>

      {/* The part no generic study list can give you. */}
      <section className="card p-4">
        <h2 className="rule-label mb-2">What else your applications ask for</h2>
        <p className="text-2xs text-navy-500 mb-3 leading-relaxed max-w-3xl">
          {home.curriculum.note}
        </p>

        {home.curriculum.needs.length === 0 && home.curriculum.total_applications === 0 && (
          <Link to="/discover" className="btn-toggle text-xs inline-flex">
            Find roles to apply to
          </Link>
        )}

        <div className="space-y-3">
          {home.curriculum.needs.map((need) => (
            <TopicRow key={need.slug} need={need} />
          ))}
        </div>

        {home.curriculum.uncatalogued.length > 0 && (
          <div className="mt-4 pt-3 border-t border-navy-100">
            <p className="text-2xs text-navy-400 leading-relaxed">
              Your postings also emphasise these, which Lighthouse has no curated route for
              yet — worth searching yourself:{" "}
              <span className="text-navy-600">
                {home.curriculum.uncatalogued.map(([term]) => term).join(", ")}
              </span>
            </p>
          </div>
        )}
      </section>

      {/* Reference, so it goes last. */}
      <section className="card p-4">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="rule-label mb-2">Your record by pattern</h2>
          {home.patterns.length > 6 && (
            <button onClick={() => setShowAll((v) => !v)} className="btn-ghost text-2xs">
              {showAll ? "Show fewer" : `Show all ${home.patterns.length}`}
            </button>
          )}
        </div>
        <div className="space-y-1.5">
          {visiblePatterns.map((p) => (
            <div key={p.slug} className="flex items-baseline gap-2 text-xs flex-wrap">
              <span
                className={`font-600 ${
                  p.is_weak ? "text-beacon-700" : p.is_untouched ? "text-navy-400" : "text-navy-800"
                }`}
              >
                {p.name}
              </span>
              <span className="text-2xs text-navy-500">{p.statement}</span>
              {p.resources[0] && (
                <a
                  href={p.resources[0].url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-2xs text-navy-400 hover:text-beacon-700 ml-auto"
                >
                  {p.resources[0].label} ↗
                </a>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function SuggestionRow({
  suggestion,
  busy,
  onLog,
}: {
  suggestion: Suggestion;
  busy: boolean;
  onLog: (slug: string, outcome: AttemptOutcome) => void;
}) {
  const { problem, reason, pattern_name } = suggestion;
  return (
    <div className="border-l-2 border-navy-200 pl-3 py-1">
      <div className="flex items-baseline gap-2 flex-wrap">
        <a
          href={problem.url}
          target="_blank"
          rel="noreferrer"
          className="text-xs font-600 text-navy-900 hover:text-beacon-700 transition-colors"
        >
          {problem.title} ↗
        </a>
        <span className={`text-2xs ${DIFFICULTY_COLOR[problem.difficulty]}`}>
          {problem.difficulty}
        </span>
        <span className="text-2xs text-navy-400">{pattern_name}</span>
      </div>
      <p className="text-2xs text-navy-500 mt-0.5 leading-relaxed">{reason}</p>
      <div className="flex flex-wrap gap-1 mt-1">
        {OUTCOMES.map((o) => (
          <button
            key={o.value}
            title={o.hint}
            disabled={busy}
            onClick={() => onLog(problem.slug, o.value)}
            className="text-2xs px-1.5 py-0.5 rounded text-navy-600 hover:text-beacon-700
                       hover:bg-beacon-glow transition-colors disabled:opacity-40"
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function TopicRow({ need }: { need: TopicNeed }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-l-2 border-beacon-500 pl-3 py-1">
      <button onClick={() => setOpen((v) => !v)} className="text-left w-full">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-xs font-600 text-navy-900">{need.name}</span>
          <span className="text-2xs text-navy-400">
            {need.hours_low}–{need.hours_high}h
          </span>
          {need.partially_covered && (
            <span className="text-2xs text-good">refresher</span>
          )}
        </div>
        <p className="text-2xs text-navy-500 mt-0.5">{need.statement}</p>
      </button>

      {open && (
        <div className="mt-2 space-y-1.5">
          <p className="text-2xs text-navy-600 leading-relaxed max-w-2xl">{need.blurb}</p>
          <p className="text-2xs text-navy-400">
            Triggered by: <span className="text-navy-600">{need.matched_terms.join(", ")}</span>
          </p>
          <ul className="space-y-0.5">
            {need.resources.map((r) => (
              <li key={r.url} className="text-2xs">
                <a
                  href={r.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-navy-700 hover:text-beacon-700 transition-colors"
                >
                  {r.label} ↗
                </a>
                <span className="text-navy-400"> · {r.kind}</span>
                {!r.is_free && <span className="text-warn"> · paid</span>}
                {r.note && <span className="text-navy-400"> — {r.note}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
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
