import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DegreeLevel, MajorOptions, Onboarding, Season, StudentProfile } from "../api/types";
import { roleLabel } from "../lib/format";

// Who you are academically. Asked in the terms a student has — a major and a
// graduation term — rather than in years of experience, which most of them
// don't have yet.
//
// The graduation term is the one that earns its place: most internships state a
// class-year window, and applying outside it is the commonest way an
// application is filtered out before anyone reads it. Once this is set,
// Lighthouse checks every posting against it.

const SEASONS: Season[] = ["winter", "spring", "summer", "fall"];

const EMPTY: StudentProfile = {
  school: null,
  major: null,
  degree_level: null,
  graduation_season: null,
  graduation_year: null,
  internships_completed: 0,
  target_role_families: [],
};

export function StudentProfileForm({
  student,
  onChange,
}: {
  student: StudentProfile | null;
  onChange: (next: Onboarding) => void;
}) {
  const [draft, setDraft] = useState<StudentProfile>(student ?? EMPTY);
  const [options, setOptions] = useState<MajorOptions | null>(null);
  const [suggested, setSuggested] = useState<string[]>([]);
  // Distinct from an empty list: a dropped request must not be reported as
  // "we don't recognise your major", which is a claim about the operator.
  const [suggestFailed, setSuggestFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.majorOptions().then(setOptions).catch(() => {});
  }, []);

  // Preview which lanes a major opens up, so the effect of answering is visible
  // before saving rather than after.
  useEffect(() => {
    const major = draft.major?.trim();
    if (!major) {
      setSuggested([]);
      setSuggestFailed(false);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      api
        .roleFamiliesFor(major)
        .then((families) => {
          if (cancelled) return;
          setSuggested(families);
          setSuggestFailed(false);
        })
        .catch(() => {
          if (cancelled) return;
          setSuggested([]);
          setSuggestFailed(true);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [draft.major]);

  const set = <K extends keyof StudentProfile>(key: K, value: StudentProfile[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const save = () => {
    setSaving(true);
    setError(null);
    api
      .saveStudentProfile(draft)
      .then((next) => {
        onChange(next);
        if (next.student) setDraft(next.student);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setSaving(false));
  };

  const gradYears = yearRange();

  return (
    <section className="card p-4 space-y-3">
      <div>
        <h3 className="text-sm font-600 text-navy-900">About you</h3>
        <p className="text-2xs text-navy-500 mt-0.5">
          Your major decides which roles Lighthouse shows by default. Your graduation term lets it
          check whether you clear each posting's class-year requirement.
        </p>
      </div>

      <label className="block">
        <span className="text-2xs text-navy-500">School</span>
        <input
          value={draft.school ?? ""}
          onChange={(e) => set("school", e.target.value || null)}
          placeholder="University of Texas at Austin"
          className="field text-xs mt-1"
        />
      </label>

      <label className="block">
        <span className="text-2xs text-navy-500">Major</span>
        <input
          value={draft.major ?? ""}
          onChange={(e) => set("major", e.target.value || null)}
          placeholder="Computer Science"
          list="lh-majors"
          className="field text-xs mt-1"
        />
        <datalist id="lh-majors">
          {options?.majors.map((m) => <option key={m} value={m} />)}
        </datalist>
        {draft.major?.trim() && (
          <p className="text-2xs text-navy-400 mt-1">
            {suggested.length > 0 ? (
              <>
                Shows you:{" "}
                <span className="text-navy-600">
                  {suggested.map((f) => roleLabel(f as never)).join(" · ")}
                </span>
              </>
            ) : suggestFailed ? (
              "Couldn't check this major just now — saving still works."
            ) : (
              "Not a major we recognise yet — you'll see every role family instead."
            )}
          </p>
        )}
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-2xs text-navy-500">Degree</span>
          <select
            value={draft.degree_level ?? ""}
            onChange={(e) => set("degree_level", (e.target.value || null) as DegreeLevel | null)}
            className="field text-xs mt-1"
          >
            <option value="">—</option>
            {options?.degree_levels.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-2xs text-navy-500">Internships done</span>
          <input
            type="number"
            min={0}
            max={20}
            value={draft.internships_completed}
            onChange={(e) => set("internships_completed", Math.max(0, Number(e.target.value) || 0))}
            className="field text-xs mt-1 tabular-nums"
          />
        </label>
      </div>

      <div>
        <span className="text-2xs text-navy-500">When you graduate</span>
        <div className="grid grid-cols-2 gap-3 mt-1">
          <select
            value={draft.graduation_season ?? ""}
            onChange={(e) => set("graduation_season", (e.target.value || null) as Season | null)}
            className="field text-xs"
          >
            <option value="">Term</option>
            {SEASONS.map((s) => (
              <option key={s} value={s}>
                {s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
          <select
            value={draft.graduation_year ?? ""}
            onChange={(e) => set("graduation_year", e.target.value ? Number(e.target.value) : null)}
            className="field text-xs tabular-nums"
          >
            <option value="">Year</option>
            {gradYears.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
        {!draft.graduation_year && (
          <p className="text-2xs text-beacon-700 mt-1">
            Worth setting — it's what catches postings that want a different class year.
          </p>
        )}
      </div>

      {error && <p className="text-2xs text-bad">{error}</p>}

      <button onClick={save} disabled={saving} className="btn-primary text-xs">
        {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
      </button>
    </section>
  );
}

/** Graduation years worth offering: last year through five ahead. */
function yearRange(): number[] {
  const now = new Date().getFullYear();
  return Array.from({ length: 7 }, (_, i) => now - 1 + i);
}
