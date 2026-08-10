import { useState } from "react";
import { api } from "../api/client";
import type { ContactInput, ParsedContact, RelationshipType } from "../api/types";

// Getting names in, the compliant way.
//
// The operator opens their school's page on LinkedIn, uses its Alumni tool,
// filters by where people work, selects the results and pastes them here.
// LinkedIn built that tool for this purpose; Lighthouse fetches nothing and
// never touches an account. What it does is the part that is actually hard —
// personalising at volume and remembering the follow-ups.
//
// Parse and save are separate steps for the same reason extraction and
// commitment are separate on the corpus page: nothing gets written until the
// operator has looked at it.

export function ContactPaste({
  school,
  onSaved,
}: {
  school: string | null;
  onSaved: (count: number) => void;
}) {
  const [text, setText] = useState("");
  const [parsed, setParsed] = useState<ParsedContact[] | null>(null);
  const [kept, setKept] = useState<Set<number>>(new Set());
  const [markAlumni, setMarkAlumni] = useState(Boolean(school));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parse = async () => {
    setBusy(true);
    setError(null);
    try {
      const rows = await api.parseContacts(text);
      setParsed(rows);
      setKept(new Set(rows.map((_, i) => i)));
      if (rows.length === 0) {
        setError(
          "Nothing recognisable in that. Each person needs a name line — a paste from the " +
            "alumni results usually works as-is.",
        );
      }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!parsed) return;
    setBusy(true);
    try {
      const payload: ContactInput[] = parsed
        .filter((_, i) => kept.has(i))
        .map((p) => ({
          name: p.name,
          role_title: p.role_title,
          company_name: p.company_name,
          school: markAlumni ? school : null,
          relationship_type: (markAlumni && school ? "alumni" : "cold") as RelationshipType,
        }));
      if (payload.length === 0) {
        onSaved(0);
        return;
      }
      await api.createContacts(payload);
      onSaved(payload.length);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card p-4 space-y-3">
      <div>
        <h2 className="text-sm font-700 text-navy-900">Add contacts</h2>
        <p className="text-2xs text-navy-500 mt-0.5 max-w-2xl leading-relaxed">
          Paste from LinkedIn's Alumni tool — your school's page, then "where they work". Names,
          roles and companies come through; locations and UI text are dropped. Nothing is saved
          until you've looked at it.
        </p>
      </div>

      {!parsed ? (
        <>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={7}
            placeholder={"Jane Doe\nSoftware Engineer at Optiver\nAustin, Texas Area\n\nMarcus Lee\nQuantitative Researcher at Jane Street"}
            className="field text-xs resize-y font-mono"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={parse}
              disabled={busy || !text.trim()}
              className="btn-primary text-xs"
            >
              {busy ? "Reading…" : "Read the paste"}
            </button>
            <span className="text-2xs text-navy-400">Saves nothing yet.</span>
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-xs text-navy-600">
              {kept.size} of {parsed.length} will be saved.
            </p>
            {school && (
              <label className="flex items-center gap-1.5 text-2xs text-navy-600">
                <input
                  type="checkbox"
                  checked={markAlumni}
                  onChange={(e) => setMarkAlumni(e.target.checked)}
                />
                These came from a {school} alumni search
              </label>
            )}
          </div>

          <ul className="space-y-1 max-h-72 overflow-y-auto">
            {parsed.map((p, i) => (
              <li key={i} className="flex items-baseline gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={kept.has(i)}
                  onChange={(e) => {
                    const next = new Set(kept);
                    e.target.checked ? next.add(i) : next.delete(i);
                    setKept(next);
                  }}
                />
                <span className="font-600 text-navy-900">{p.name}</span>
                <span className="text-2xs text-navy-400">
                  {[p.role_title, p.company_name].filter(Boolean).join(" · ") || "no role read"}
                </span>
              </li>
            ))}
          </ul>

          <div className="flex items-center gap-2">
            <button onClick={save} disabled={busy || kept.size === 0} className="btn-primary text-xs">
              {busy ? "Saving…" : `Save ${kept.size}`}
            </button>
            <button
              onClick={() => {
                setParsed(null);
                setError(null);
              }}
              className="btn-toggle text-xs"
            >
              Back
            </button>
          </div>
        </>
      )}

      {error && <p className="text-2xs text-bad leading-relaxed">{error}</p>}
    </section>
  );
}
