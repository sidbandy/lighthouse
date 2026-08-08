import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AtsReport } from "../api/types";
import { AtsFindings } from "./AtsFindings";
import { ParsePreview } from "./ParsePreview";

// The resume checker page. The upload is deliberately the whole hero: this is
// the "will I even get seen?" question, and it should feel like the first thing
// worth doing.

export function ResumeCheck() {
  const [report, setReport] = useState<AtsReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const run = useCallback((file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Upload a PDF. Most ATS only reliably read PDFs.");
      return;
    }
    setFileName(file.name);
    setError(null);
    setReport(null);
    setLoading(true);
    api
      .checkResume(file)
      .then(setReport)
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-6 py-6 space-y-6">
      <div>
        <h1 className="text-lg font-700 text-navy-900">Will your resume reach a human?</h1>
        <p className="text-sm text-navy-500 mt-1">
          Before a recruiter sees it, an ATS extracts your resume into text. If that extraction
          garbles or drops your content, you are rejected by a machine. This checks the extraction
          the way the parser does — and shows you exactly what it sees.
        </p>
      </div>

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
        className={`card flex flex-col items-center justify-center py-10 cursor-pointer border-dashed
                    transition-colors ${
                      dragging ? "border-beacon-500 bg-beacon-glow" : "hover:border-navy-300"
                    }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && run(e.target.files[0])}
        />
        <div className="text-2xl mb-2 text-navy-500">↑</div>
        <p className="text-sm text-navy-800">
          {fileName ? <span className="text-navy-900">{fileName}</span> : "Drop your resume PDF here"}
        </p>
        <p className="text-2xs text-navy-500 mt-1">or click to choose · nothing is stored</p>
      </label>

      {loading && (
        <div className="text-center text-sm text-navy-500 py-6">Reading it the way an ATS would…</div>
      )}

      {error && (
        <div className="card border-bad/30 bg-bad/5 p-4 text-sm text-bad">{error}</div>
      )}

      {report && (
        <div className="space-y-5 animate-fade-in">
          <Verdict report={report} />
          <SaveVersion report={report} fileName={fileName} />
          {report.preview && <ParsePreview preview={report.preview} />}
          <div>
            <h3 className="text-2xs font-600 uppercase tracking-wide text-navy-600 mb-2">
              {report.findings.length > 0 ? "What to fix, worst first" : "Findings"}
            </h3>
            <AtsFindings findings={report.findings} />
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Record this résumé as a version, so the board can say which one went where.
 *
 * Worth the extra click: a funnel over one undifferentiated pile can tell you
 * how the search is going, but not whether the rewrite did anything. That
 * comparison is most of what version tracking is for.
 */
function SaveVersion({ report, fileName }: { report: AtsReport; fileName: string | null }) {
  const suggested = (fileName ?? "").replace(/\.pdf$/i, "");
  const [label, setLabel] = useState(suggested);
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLabel(suggested);
    setState("idle");
  }, [suggested]);

  if (state === "saved") {
    return (
      <p className="text-2xs text-good">
        ✓ Saved as “{label}”. Pick it on an application to record that this is the one you sent.
      </p>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <input
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="Name this version, e.g. “v3 — security lead”"
        className="field text-xs flex-1 min-w-[16rem]"
      />
      <button
        className="btn-toggle text-xs shrink-0"
        disabled={state === "saving" || !label.trim()}
        title="Record this résumé so the board can track which applications used it"
        onClick={() => {
          setState("saving");
          setError(null);
          api
            .saveResumeVersion({
              label: label.trim(),
              extracted_text: report.preview?.ats_text ?? "",
            })
            .then(() => setState("saved"))
            .catch((e) => {
              setError(String((e as Error).message ?? e));
              setState("idle");
            });
        }}
      >
        {state === "saving" ? "Saving…" : "Save as a version"}
      </button>
      {error && <span className="text-2xs text-bad">{error}</span>}
    </div>
  );
}

function Verdict({ report }: { report: AtsReport }) {
  const clean = report.will_parse_cleanly;
  return (
    <div
      className={`card p-4 border ${
        clean ? "border-good/30 bg-good/5" : "border-bad/30 bg-bad/5"
      }`}
    >
      <div className="flex items-center gap-3">
        <span className={`text-2xl ${clean ? "text-good" : "text-bad"}`}>{clean ? "✓" : "✕"}</span>
        <div>
          <p className="text-sm font-600 text-navy-900">{report.verdict}</p>
          <p className="text-2xs text-navy-500 mt-0.5">
            {report.page_count} page{report.page_count !== 1 ? "s" : ""} · {report.word_count} words
            extracted · {report.fonts.length} font{report.fonts.length !== 1 ? "s" : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
