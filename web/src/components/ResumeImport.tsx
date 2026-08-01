import { useCallback, useState } from "react";
import { api } from "../api/client";
import type { DraftFact, Extraction, FactInput, FactType } from "../api/types";
import { FACT_TYPES } from "./FactEditor";

// Resume → draft facts → the operator's review → corpus.
//
// The review step is not a formality. Extraction is heuristic: it guesses where
// one entry ends and the next begins, and it will sometimes split a bullet in
// half or file a project under experience. Every draft is therefore editable and
// discardable, and *nothing* reaches the corpus until the operator says so —
// the corpus may only contain things they'd defend in an interview.

type Draft = DraftFact & { id: number; keep: boolean };

export function ResumeImport({ onImported }: { onImported: (count: number) => void }) {
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [fileName, setFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const run = useCallback((file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Upload a PDF — that's what the extractor reads.");
      return;
    }
    setFileName(file.name);
    setError(null);
    setExtraction(null);
    setDrafts([]);
    setLoading(true);
    api
      .extractResume(file)
      .then((result) => {
        setExtraction(result);
        setDrafts(result.drafts.map((d, i) => ({ ...d, id: i, keep: true })));
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
  }, []);

  const kept = drafts.filter((d) => d.keep);

  const commit = () => {
    setSaving(true);
    setError(null);
    const payload: FactInput[] = kept.map((d) => ({
      fact_type: d.fact_type,
      title: d.title,
      body: d.body,
    }));
    api
      .createFacts(payload)
      .then((saved) => {
        onImported(saved.length);
        setExtraction(null);
        setDrafts([]);
        setFileName(null);
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setSaving(false));
  };

  const patch = (id: number, changes: Partial<Draft>) =>
    setDrafts((ds) => ds.map((d) => (d.id === id ? { ...d, ...changes } : d)));

  return (
    <section className="space-y-3">
      {!extraction && (
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (e.dataTransfer.files[0]) run(e.dataTransfer.files[0]);
          }}
          className={`card flex flex-col items-center justify-center py-8 cursor-pointer border-dashed
                      transition-colors ${
                        dragging ? "border-beacon-500 bg-beacon-glow" : "hover:border-ink-600"
                      }`}
        >
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && run(e.target.files[0])}
          />
          <div className="text-xl mb-1.5 text-mist-400">↑</div>
          <p className="text-sm text-mist-200">
            {fileName ? (
              <span className="text-mist-100">{fileName}</span>
            ) : (
              "Start from your résumé"
            )}
          </p>
          <p className="text-2xs text-mist-400 mt-1">
            drop a PDF or click · you review everything before it's saved
          </p>
        </label>
      )}

      {loading && <p className="text-sm text-mist-400 text-center py-4">Reading your résumé…</p>}

      {error && <div className="card border-bad/30 bg-bad/5 p-3 text-xs text-bad">{error}</div>}

      {extraction && (
        <div className="space-y-3 animate-fade-in">
          <div
            className={`card p-3 border ${
              extraction.likely_image_based ? "border-warn/30 bg-warn/5" : "border-ink-700/70"
            }`}
          >
            <p
              className={`text-xs leading-relaxed ${
                extraction.likely_image_based ? "text-warn" : "text-mist-300"
              }`}
            >
              {extraction.note}
            </p>
            <p className="text-2xs text-mist-500 mt-1">
              {extraction.page_count} page{extraction.page_count !== 1 ? "s" : ""} ·{" "}
              {extraction.char_count.toLocaleString()} characters extracted
            </p>
          </div>

          {drafts.length > 0 && (
            <>
              <div className="flex items-center justify-between">
                <span className="text-2xs text-mist-400">
                  {kept.length} of {drafts.length} selected
                </span>
                <div className="flex gap-1">
                  <button
                    onClick={() => setDrafts((ds) => ds.map((d) => ({ ...d, keep: true })))}
                    className="btn-ghost text-2xs px-2 py-1"
                  >
                    Select all
                  </button>
                  <button
                    onClick={() => setDrafts((ds) => ds.map((d) => ({ ...d, keep: false })))}
                    className="btn-ghost text-2xs px-2 py-1"
                  >
                    None
                  </button>
                </div>
              </div>

              <div className="space-y-1.5 max-h-[28rem] overflow-y-auto pr-1">
                {drafts.map((draft) => (
                  <DraftRow key={draft.id} draft={draft} onChange={patch} />
                ))}
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={commit}
                  disabled={saving || kept.length === 0}
                  className="btn-primary text-xs"
                >
                  {saving
                    ? "Saving…"
                    : `Save ${kept.length} fact${kept.length !== 1 ? "s" : ""} to my corpus`}
                </button>
                <button
                  onClick={() => {
                    setExtraction(null);
                    setDrafts([]);
                    setFileName(null);
                  }}
                  className="btn-ghost text-xs"
                >
                  Discard
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

function DraftRow({
  draft,
  onChange,
}: {
  draft: Draft;
  onChange: (id: number, changes: Partial<Draft>) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`card p-2.5 transition-opacity ${draft.keep ? "" : "opacity-40"}`}
    >
      <div className="flex items-start gap-2.5">
        <input
          type="checkbox"
          checked={draft.keep}
          onChange={(e) => onChange(draft.id, { keep: e.target.checked })}
          className="mt-1 accent-beacon-500 shrink-0 cursor-pointer"
        />
        <div className="flex-1 min-w-0">
          {expanded ? (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-1">
                {FACT_TYPES.map((t) => (
                  <button
                    key={t.value}
                    onClick={() => onChange(draft.id, { fact_type: t.value as FactType })}
                    className={
                      draft.fact_type === t.value
                        ? "btn-toggle-on text-2xs"
                        : "btn-toggle text-2xs"
                    }
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <input
                value={draft.title}
                onChange={(e) => onChange(draft.id, { title: e.target.value })}
                className="w-full text-xs bg-ink-950 border border-ink-700 rounded px-2 py-1.5
                           text-mist-100 focus:border-ink-600 outline-none"
              />
              <textarea
                value={draft.body}
                onChange={(e) => onChange(draft.id, { body: e.target.value })}
                placeholder="Detail — correct anything the extractor got wrong."
                className="w-full h-20 text-2xs bg-ink-950 border border-ink-700 rounded p-2
                           text-mist-200 placeholder:text-mist-500 focus:border-ink-600 outline-none
                           resize-y leading-relaxed"
              />
            </div>
          ) : (
            <button onClick={() => setExpanded(true)} className="text-left w-full">
              <div className="flex items-baseline gap-2">
                <span className="chip border-ink-700 text-mist-500 shrink-0">
                  {draft.fact_type}
                </span>
                <span className="text-xs text-mist-200 truncate">{draft.title}</span>
              </div>
              {draft.body && (
                <p className="text-2xs text-mist-500 mt-1 line-clamp-2 leading-relaxed">
                  {draft.body}
                </p>
              )}
            </button>
          )}
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="btn-ghost text-2xs px-1.5 py-0.5 shrink-0"
        >
          {expanded ? "Done" : "Edit"}
        </button>
      </div>
    </div>
  );
}
