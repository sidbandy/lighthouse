import { useEffect, useRef, useState } from "react";
import type { FactInput, FactType } from "../api/types";

// The form for one fact, used for both new facts and edits. Deliberately plain:
// the operator writes their own material, and anything that nudged them toward
// wording they can't back up would defeat the point of the corpus.

export const FACT_TYPES: { value: FactType; label: string; hint: string }[] = [
  { value: "project", label: "Project", hint: "something you built, with what it did and how" },
  { value: "experience", label: "Experience", hint: "a job, internship, lab or club role" },
  { value: "skill", label: "Skill", hint: "a tool or method you'd defend in an interview" },
  { value: "achievement", label: "Achievement", hint: "an award, publication or competition" },
  { value: "education", label: "Education", hint: "a degree, and the coursework that matters" },
];

const BODY_PLACEHOLDER: Record<FactType, string> = {
  project:
    "What it does, what you built it with, and what happened as a result. Concrete beats polished — the words here are what gets matched against postings.",
  experience:
    "What you actually did, in your own words. One line per thing, the way you'd say it out loud.",
  skill: "Optional: where you used it, and how far you'd trust yourself with it.",
  achievement: "What it was, and what you did to get it.",
  education: "Degree, institution, and the coursework worth naming.",
};

export function FactEditor({
  initial,
  onSave,
  onCancel,
  saving = false,
  autoFocus = false,
}: {
  initial?: Partial<FactInput>;
  onSave: (fact: FactInput) => void;
  onCancel: () => void;
  saving?: boolean;
  autoFocus?: boolean;
}) {
  const [factType, setFactType] = useState<FactType>(initial?.fact_type ?? "project");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (autoFocus) titleRef.current?.focus();
  }, [autoFocus]);

  const valid = title.trim().length > 0;

  const submit = () => {
    if (!valid || saving) return;
    onSave({
      fact_type: factType,
      title: title.trim(),
      body: body.trim(),
      metadata: initial?.metadata ?? {},
    });
  };

  return (
    <div
      className="space-y-2.5"
      onKeyDown={(e) => {
        if (e.key === "Escape") onCancel();
        // Cmd/Ctrl+Enter saves — this form gets used repeatedly when reviewing
        // a whole resume, and reaching for the mouse each time is friction.
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
      }}
    >
      <div className="flex flex-wrap gap-1">
        {FACT_TYPES.map((t) => (
          <button
            key={t.value}
            onClick={() => setFactType(t.value)}
            title={t.hint}
            className={factType === t.value ? "btn-toggle-on text-2xs" : "btn-toggle text-2xs"}
          >
            {t.label}
          </button>
        ))}
      </div>

      <input
        ref={titleRef}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={
          factType === "skill" ? "e.g. PostgreSQL" : "e.g. Ledger — personal finance tracker"
        }
        className="w-full text-sm bg-ink-950 border border-ink-700 rounded-lg px-2.5 py-2
                   text-mist-100 placeholder:text-mist-500 focus:border-ink-600 outline-none"
      />

      {factType !== "skill" || body ? (
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={BODY_PLACEHOLDER[factType]}
          className="w-full h-24 text-xs bg-ink-950 border border-ink-700 rounded-lg p-2.5
                     text-mist-200 placeholder:text-mist-500 focus:border-ink-600 outline-none resize-y
                     leading-relaxed"
        />
      ) : (
        <button
          onClick={() => setBody(" ")}
          className="text-2xs text-mist-500 hover:text-mist-300 transition-colors"
        >
          + add detail
        </button>
      )}

      <div className="flex items-center gap-2">
        <button onClick={submit} disabled={!valid || saving} className="btn-primary text-xs">
          {saving ? "Saving…" : "Save"}
        </button>
        <button onClick={onCancel} className="btn-ghost text-xs">
          Cancel
        </button>
        <span className="text-2xs text-mist-500 ml-auto">⌘↵ to save · esc to cancel</span>
      </div>
    </div>
  );
}
