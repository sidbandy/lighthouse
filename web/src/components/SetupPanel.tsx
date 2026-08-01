import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  CompanySuggestion,
  Constraints,
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
      <TargetPicker targets={onboarding.targets} onChange={onChange} />
      <ConstraintsForm constraints={onboarding.constraints} onChange={onChange} />
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
        <h3 className="text-sm font-600 text-mist-100">Target companies</h3>
        <p className="text-2xs text-mist-400 mt-0.5">
          Places you actually want. Marking one never changes how selective it is — Lighthouse
          won't tell you a reach is realistic because you'd like it to be.
        </p>
      </div>

      <div className="relative">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search companies…"
          className="w-full text-xs bg-ink-950 border border-ink-700 rounded-lg px-2.5 py-2
                     text-mist-100 placeholder:text-mist-500 focus:border-ink-600 outline-none"
        />
        {results.length > 0 && (
          <div className="absolute z-20 mt-1 w-full card p-1 shadow-lift max-h-56 overflow-y-auto">
            {results.map((r) => (
              <button
                key={r.canonical_name}
                onClick={() => add(r.name)}
                disabled={r.is_target}
                className="w-full flex items-center justify-between gap-2 px-2 py-1.5 rounded-md
                           text-left hover:bg-ink-800 disabled:opacity-40 transition-colors"
              >
                <span className="text-xs text-mist-200 truncate">{r.name}</span>
                <span className="text-2xs text-mist-500 shrink-0 tabular-nums">
                  {r.is_target ? "already a target" : `${r.posting_count} live`}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-2xs text-bad">{error}</p>}

      {targets.length === 0 ? (
        <p className="text-2xs text-mist-500">
          No targets yet. They seed the three-lane view and tell Lighthouse which boards to poll
          directly.
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {targets.map((t) => (
            <span
              key={t.id}
              className="chip border-ink-600 bg-ink-800 group"
              title={`Selectivity ${t.selectivity}/4 — ${SELECTIVITY_LABEL[t.selectivity] ?? "unknown"}`}
            >
              <span className="text-mist-200">{t.name}</span>
              <span className="text-mist-500">{SELECTIVITY_LABEL[t.selectivity] ?? "—"}</span>
              <button
                onClick={() => remove(t.name)}
                disabled={saving}
                className="text-mist-500 hover:text-bad transition-colors ml-0.5"
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
  onChange,
}: {
  constraints: Constraints | null;
  onChange: (next: Onboarding) => void;
}) {
  const [draft, setDraft] = useState<Constraints>(
    constraints ?? {
      preferred_locations: [],
      open_to_remote: true,
      sponsorship: "us_authorized",
      weekly_study_hours: 10,
      target_cycles: [],
    },
  );
  const [locationText, setLocationText] = useState(
    (constraints?.preferred_locations ?? []).join(", "),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

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
        <h3 className="text-sm font-600 text-mist-100">What you're looking for</h3>
        <p className="text-2xs text-mist-400 mt-0.5">
          Seeds your filters and, later, the study plan.
        </p>
      </div>

      <label className="block">
        <span className="text-2xs text-mist-400">Preferred locations</span>
        <input
          value={locationText}
          onChange={(e) => setLocationText(e.target.value)}
          placeholder="Austin TX, New York, Remote"
          className="w-full mt-1 text-xs bg-ink-950 border border-ink-700 rounded-lg px-2.5 py-2
                     text-mist-100 placeholder:text-mist-500 focus:border-ink-600 outline-none"
        />
        <span className="text-2xs text-mist-500">comma separated</span>
      </label>

      <div>
        <span className="text-2xs text-mist-400">Work authorization</span>
        <div className="flex flex-col gap-1 mt-1">
          {SPONSORSHIP.map((s) => (
            <button
              key={s.value}
              onClick={() => setDraft({ ...draft, sponsorship: s.value })}
              className={`text-left px-2.5 py-1.5 rounded-lg border transition-colors ${
                draft.sponsorship === s.value
                  ? "border-beacon-500/50 bg-beacon-glow"
                  : "border-ink-700 hover:border-ink-600"
              }`}
            >
              <div
                className={`text-xs ${
                  draft.sponsorship === s.value ? "text-beacon-400" : "text-mist-200"
                }`}
              >
                {s.label}
              </div>
              <div className="text-2xs text-mist-500">{s.hint}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={draft.open_to_remote}
            onChange={(e) => setDraft({ ...draft, open_to_remote: e.target.checked })}
            className="accent-beacon-500 cursor-pointer"
          />
          <span className="text-xs text-mist-300">Open to remote</span>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-xs text-mist-300">Study hrs/week</span>
          <input
            type="number"
            min={0}
            max={168}
            value={draft.weekly_study_hours}
            onChange={(e) =>
              setDraft({ ...draft, weekly_study_hours: Number(e.target.value) || 0 })
            }
            className="w-16 text-xs bg-ink-950 border border-ink-700 rounded px-2 py-1
                       text-mist-100 focus:border-ink-600 outline-none tabular-nums"
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
