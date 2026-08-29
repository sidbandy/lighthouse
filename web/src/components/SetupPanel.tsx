import { useEffect, useState } from "react";
import { api } from "../api/client";
import { StudentProfileForm } from "./StudentProfileForm";
import type {
  CompanySuggestion,
  Constraints,
  CycleCount,
  Onboarding,
  SponsorshipStance,
  TargetCompany,
} from "../api/types";

// Target companies and constraints — the last two onboarding steps.
//
// The target picker searches the companies already ingested and shows how many
// live postings each has, so targets are chosen against real supply rather than
// from memory. Marking a target says nothing about how hard the company is to
// get into: selectivity is shown beside it and is never changed by wanting it.

const SELECTIVITY_LABEL: Record<number, string> = {
  4: "highly selective",
  3: "very competitive",
  2: "competitive",
  1: "more accessible",
};

const SPONSORSHIP: { value: SponsorshipStance; label: string; hint: string }[] = [
  {
    value: "us_citizen",
    label: "US citizen",
    hint: "clears citizenship-required roles (defense, some finance)",
  },
  { value: "us_authorized", label: "Authorized to work in the US", hint: "no sponsorship needed" },
  {
    value: "needs_sponsorship",
    label: "Will need sponsorship",
    hint: "filters out roles that state they don't sponsor",
  },
];

export function SetupPanel({
  onboarding,
  onChange,
}: {
  onboarding: Onboarding;
  onChange: (next: Onboarding) => void;
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <StudentProfileForm student={onboarding.student} onChange={onChange} />
      <ConstraintsForm
        constraints={onboarding.constraints}
        suggested={onboarding.suggested_constraints}
        onChange={onChange}
      />
      <TargetPicker targets={onboarding.targets} onChange={onChange} />
    </div>
  );
}

function TargetPicker({
  targets,
  onChange,
}: {
  targets: TargetCompany[];
  onChange: (next: Onboarding) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompanySuggestion[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    // Debounced so typing a company name doesn't fire a request per keystroke.
    const timer = setTimeout(() => {
      api
        .searchCompanies(query.trim(), 8)
        .then(setResults)
        .catch(() => setResults([]));
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  const save = (names: string[]) => {
    setSaving(true);
    setError(null);
    api
      .saveTargets(names)
      .then(onChange)
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setSaving(false));
  };

  const add = (name: string) => {
    if (targets.some((t) => t.name === name)) return;
    save([...targets.map((t) => t.name), name]);
    setQuery("");
    setResults([]);
  };

  const remove = (name: string) => save(targets.filter((t) => t.name !== name).map((t) => t.name));

  return (
    <section className="card p-4 space-y-3">
      <div>
        <h3 className="text-sm font-600 text-navy-900">Target companies</h3>
        <p className="text-2xs text-navy-500 mt-0.5">
          Places you actually want. Marking one never changes how selective it is — Lighthouse
          won't tell you a reach is realistic because you'd like it to be.
        </p>
      </div>

      <div className="relative">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search companies…"
          className="field text-xs"
        />
        {results.length > 0 && (
          <div className="absolute z-20 mt-1 w-full card p-1 shadow-lift max-h-56 overflow-y-auto">
            {results.map((r) => (
              <button
                key={r.canonical_name}
                onClick={() => add(r.name)}
                disabled={r.is_target}
                className="w-full flex items-center justify-between gap-2 px-2 py-1.5 rounded-md
                           text-left hover:bg-navy-100 disabled:opacity-40 transition-colors"
              >
                <span className="text-xs text-navy-800 truncate">{r.name}</span>
                <span className="text-2xs text-navy-400 shrink-0 tabular-nums">
                  {r.is_target ? "already a target" : `${r.posting_count} live`}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-2xs text-bad">{error}</p>}

      {targets.length === 0 ? (
        <p className="text-2xs text-navy-400">
          No targets yet. They seed the three-lane view and tell Lighthouse which boards to poll
          directly.
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {targets.map((t) => (
            <span
              key={t.id}
              className="chip border-navy-300 bg-navy-100 group"
              title={`Selectivity ${t.selectivity}/4 — ${SELECTIVITY_LABEL[t.selectivity] ?? "unknown"}`}
            >
              <span className="text-navy-800">{t.name}</span>
              <span className="text-navy-400">{SELECTIVITY_LABEL[t.selectivity] ?? "—"}</span>
              <button
                onClick={() => remove(t.name)}
                disabled={saving}
                className="text-navy-400 hover:text-bad transition-colors ml-0.5"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function ConstraintsForm({
  constraints,
  suggested,
  onChange,
}: {
  constraints: Constraints | null;
  suggested: Constraints | null;
  onChange: (next: Onboarding) => void;
}) {
  // Saved answer first; the server's suggestion only when there is none. The
  // literal is the last resort, for an older API that sends neither.
  const [draft, setDraft] = useState<Constraints>(
    constraints ??
      suggested ?? {
        preferred_locations: [],
        open_to_remote: true,
        sponsorship: "us_authorized",
        weekly_study_hours: 10,
        target_cycles: [],
      },
  );
  const [locationText, setLocationText] = useState(
    (constraints?.preferred_locations ?? suggested?.preferred_locations ?? []).join(", "),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [cycles, setCycles] = useState<CycleCount[] | null>(null);

  // The same still-applyable cycles Discover filters by, with their live
  // posting counts, so the choice is made against real supply.
  useEffect(() => {
    api.cycles().then(setCycles).catch(() => setCycles([]));
  }, []);

  const toggleCycle = (label: string) =>
    setDraft((d) => ({
      ...d,
      target_cycles: d.target_cycles.includes(label)
        ? d.target_cycles.filter((c) => c !== label)
        : [...d.target_cycles, label],
    }));

  const save = () => {
    setSaving(true);
    setError(null);
    const payload: Constraints = {
      ...draft,
      preferred_locations: locationText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    api
      .saveConstraints(payload)
      .then((next) => {
        onChange(next);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setSaving(false));
  };

  return (
    <section className="card p-4 space-y-3">
      <div>
        <h3 className="text-sm font-600 text-navy-900">What you're looking for</h3>
        <p className="text-2xs text-navy-500 mt-0.5">
          Seeds your filters and, later, the study plan.
        </p>
      </div>

      <label className="block">
        <span className="text-2xs text-navy-500">Preferred locations</span>
        <input
          value={locationText}
          onChange={(e) => setLocationText(e.target.value)}
          placeholder="Austin TX, New York, Remote"
          className="field text-xs mt-1"
        />
        <span className="text-2xs text-navy-400">comma separated</span>
      </label>

      <div>
        <span className="text-2xs text-navy-500">Work authorization</span>
        <div className="flex flex-col gap-1 mt-1">
          {SPONSORSHIP.map((s) => (
            <button
              key={s.value}
              onClick={() => setDraft({ ...draft, sponsorship: s.value })}
              className={`text-left px-2.5 py-1.5 rounded-lg border transition-colors ${
                draft.sponsorship === s.value
                  ? "border-beacon-500/50 bg-beacon-glow"
                  : "border-navy-200 hover:border-navy-300"
              }`}
            >
              <div
                className={`text-xs ${
                  draft.sponsorship === s.value ? "text-beacon-600" : "text-navy-800"
                }`}
              >
                {s.label}
              </div>
              <div className="text-2xs text-navy-400">{s.hint}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Cycles were previously saved as an empty list for every operator with
          no way to see or change them, while still seeding filters. Shown here
          because a filter the operator cannot see is a filter they cannot
          correct. */}
      <div>
        <span className="text-2xs text-navy-500">Cycles you're applying to</span>
        {cycles === null ? (
          <p className="text-2xs text-navy-400 mt-1">Loading cycles…</p>
        ) : cycles.length === 0 ? (
          <p className="text-2xs text-navy-400 mt-1">
            No applyable cycles right now — refresh postings, or check back after the next
            ingest.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5 mt-1">
              {cycles.map((c) => {
                const on = draft.target_cycles.includes(c.term_label);
                return (
                  <button
                    key={c.term_label}
                    onClick={() => toggleCycle(c.term_label)}
                    aria-pressed={on}
                    className={`px-2 py-1 rounded-lg border text-2xs transition-colors ${
                      on
                        ? "border-beacon-500/50 bg-beacon-glow text-beacon-600"
                        : "border-navy-200 text-navy-600 hover:border-navy-300"
                    }`}
                  >
                    {c.term_label}{" "}
                    <span className="tabular-nums text-navy-400">{c.count}</span>
                  </button>
                );
              })}
            </div>
            {!constraints && (
              <p className="text-2xs text-navy-400 mt-1">
                The soonest few are preselected as a starting point — nothing is saved
                until you press Save.
              </p>
            )}
          </>
        )}
      </div>

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={draft.open_to_remote}
            onChange={(e) => setDraft({ ...draft, open_to_remote: e.target.checked })}
            className="accent-beacon-500 cursor-pointer"
          />
          <span className="text-xs text-navy-600">Open to remote</span>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-xs text-navy-600">Study hrs/week</span>
          <input
            type="number"
            min={0}
            max={168}
            value={draft.weekly_study_hours}
            onChange={(e) =>
              setDraft({ ...draft, weekly_study_hours: Number(e.target.value) || 0 })
            }
            className="field text-xs w-16 px-2 py-1 tabular-nums"
          />
        </label>
      </div>

      {error && <p className="text-2xs text-bad">{error}</p>}

      <button onClick={save} disabled={saving} className="btn-primary text-xs">
        {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
      </button>
    </section>
  );
}
