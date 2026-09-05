import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { BriefItem, BriefSection, TriageGroup, WeeklyBrief } from "../api/types";

// The week in one place.
//
// This page adds nothing. Every line on it was computed by the module that owns
// it — follow-ups by the cadence engine, silence by the board, reviews by SRS,
// gaps by the story bank — and the briefing's whole job is to put them in the
// order they should be worked so the operator stops holding the season in their
// head.
//
// Which means the empty states are the feature, not the fallback. "Nothing is
// due" and "you have not added anything yet" are different sentences and the
// difference is what stops the page lying to a new user.

const BAND_TONE: Record<string, string> = {
  deep: "border-beacon-500/40 bg-beacon-glow",
  standard: "border-navy-200",
  light: "border-navy-100",
};

const BAND_LABEL: Record<string, string> = {
  deep: "Deep work",
  standard: "Standard",
  light: "Light touch",
};

function dueLabel(item: BriefItem): string | null {
  if (!item.due_on) return null;
  const due = new Date(item.due_on + "T00:00:00");
  const days = Math.round((due.getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days < 0) return `${Math.abs(days)}d late`;
  return `in ${days}d`;
}

function Section({ section }: { section: BriefSection }) {
  return (
    <section className="card p-4">
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <h2 className="rule-label">{section.title}</h2>
        {section.count > 0 && (
          <span className="text-2xs text-navy-400 tabular-nums">{section.count}</span>
        )}
      </div>

      {section.count === 0 ? (
        <p className="text-xs text-navy-500 leading-relaxed">{section.empty_note}</p>
      ) : (
        <ul className="space-y-2">
          {section.items.map((item, i) => {
            const due = dueLabel(item);
            return (
              <li key={`${item.kind}-${i}`} className="flex items-baseline gap-2.5">
                {/* The beacon is rationed: only genuinely late work earns it. */}
                <span
                  className={`mt-1.5 h-1.5 w-1.5 rounded-full shrink-0 ${
                    item.is_late ? "bg-beacon-500" : "bg-navy-200"
                  }`}
                  aria-hidden="true"
                />
                <div className="flex-1 min-w-0">
                  <Link
                    to={item.link}
                    className="text-sm text-navy-900 hover:text-beacon-600 transition-colors"
                  >
                    {item.title}
                  </Link>
                  {item.detail && (
                    <p className="text-2xs text-navy-500 mt-0.5 leading-relaxed">{item.detail}</p>
                  )}
                </div>
                {due && (
                  <span
                    className={`text-2xs shrink-0 tabular-nums ${
                      item.is_late ? "text-beacon-600 font-600" : "text-navy-400"
                    }`}
                  >
                    {due}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function TriagePanel({ groups }: { groups: TriageGroup[] }) {
  const total = groups.reduce((n, g) => n + g.count, 0);

  return (
    <section className="card p-4">
      <h2 className="rule-label mb-2">How much each application is worth</h2>
      {total === 0 ? (
        <p className="text-xs text-navy-500 leading-relaxed">
          Nothing live yet. Once you have applications in flight this sorts them by how far
          each has actually got — an interview next week earns real study, something sent
          yesterday earns none yet.
        </p>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => (
            <div key={group.band}>
              <div className="flex items-baseline gap-2">
                <span className="text-xs font-600 text-navy-800 whitespace-nowrap">
                  {BAND_LABEL[group.band]}
                </span>
                <span className="text-2xs text-navy-400 tabular-nums">{group.count}</span>
                <span className="text-2xs text-navy-400">· {group.blurb}</span>
              </div>
              {group.count === 0 ? (
                <p className="text-2xs text-navy-400 mt-1 italic">Nothing in this band.</p>
              ) : (
                <ul className="mt-1.5 space-y-1.5">
                  {group.applications.map((a) => (
                    <li
                      key={a.application_id}
                      className={`border-l-2 pl-2.5 py-0.5 ${BAND_TONE[a.band] ?? ""}`}
                    >
                      <Link
                        to="/applications"
                        className="text-xs text-navy-900 hover:text-beacon-600 transition-colors"
                      >
                        {a.posting_title}
                        <span className="text-navy-500"> · {a.company_name}</span>
                      </Link>
                      <p className="text-2xs text-navy-500 mt-0.5">
                        {a.stage_label} — {a.reason}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function BriefingPage() {
  const [brief, setBrief] = useState<WeeklyBrief | null>(null);
  const [triage, setTriage] = useState<TriageGroup[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.weeklyBrief(), api.triage()])
      .then(([b, t]) => {
        setBrief(b);
        setTriage(t);
      })
      .catch((e) => setError(String((e as Error).message ?? e)));
  }, []);

  if (error) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-6">
        <p className="text-sm text-bad">Could not build this week's briefing. {error}</p>
      </div>
    );
  }

  if (!brief || !triage) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-6">
        <p className="text-sm text-navy-500">Assembling the week…</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-6 space-y-4">
      <div>
        <h1 className="text-lg font-700 text-navy-900">This week</h1>
        <p className="text-sm text-navy-500 mt-1 leading-relaxed">
          Everything due, in the order it should be worked. Nothing here is scored or
          predicted — every line is a dated fact with the reason attached.
        </p>
      </div>

      <div className="card p-4 border-beacon-500/30 bg-beacon-glow">
        <p className="text-sm text-navy-900">{brief.headline}</p>
        <p className="text-2xs text-navy-500 mt-1">
          Built for {new Date(brief.generated_for + "T00:00:00").toLocaleDateString(undefined, {
            weekday: "long",
            month: "long",
            day: "numeric",
          })}
        </p>
      </div>

      {brief.sections.map((s) => (
        <Section key={s.key} section={s} />
      ))}

      <TriagePanel groups={triage} />

      {/* Both notes exist to say what is *not* being shown. They are the
          reason the numbers above can be trusted, so they stay on the page
          rather than behind a tooltip. */}
      {(brief.funnel_note || brief.baseline_note) && (
        <section className="card p-4 space-y-1.5">
          <h2 className="rule-label mb-1">What these numbers rest on</h2>
          {brief.funnel_note && (
            <p className="text-2xs text-navy-500 leading-relaxed">{brief.funnel_note}</p>
          )}
          {brief.baseline_note && (
            <p className="text-2xs text-navy-500 leading-relaxed">{brief.baseline_note}</p>
          )}
        </section>
      )}
    </div>
  );
}
