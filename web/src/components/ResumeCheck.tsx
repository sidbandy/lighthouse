import { useCallback, useRef, useState } from "react";
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
        <h1 className="text-lg font-700 text-mist-100">Will your resume reach a human?</h1>
        <p className="text-sm text-mist-400 mt-1">
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
                      dragging ? "border-beacon-500 bg-beacon-glow" : "hover:border-ink-600"
                    }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && run(e.target.files[0])}
        />
        <div className="text-2xl mb-2 text-mist-400">↑</div>
        <p className="text-sm text-mist-200">
          {fileName ? <span className="text-mist-100">{fileName}</span> : "Drop your resume PDF here"}
        </p>
        <p className="text-2xs text-mist-400 mt-1">or click to choose · nothing is stored</p>
      </label>

      {loading && (
        <div className="text-center text-sm text-mist-400 py-6">Reading it the way an ATS would…</div>
      )}

      {error && (
        <div className="card border-bad/30 bg-bad/5 p-4 text-sm text-bad">{error}</div>
      )}

      {report && (
        <div className="space-y-5 animate-fade-in">
          <Verdict report={report} />
          {report.preview && <ParsePreview preview={report.preview} />}
          <div>
            <h3 className="text-2xs font-600 uppercase tracking-wide text-mist-300 mb-2">
              {report.findings.length > 0 ? "What to fix, worst first" : "Findings"}
            </h3>
            <AtsFindings findings={report.findings} />
          </div>
        </div>
      )}
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
          <p className="text-sm font-600 text-mist-100">{report.verdict}</p>
          <p className="text-2xs text-mist-400 mt-0.5">
            {report.page_count} page{report.page_count !== 1 ? "s" : ""} · {report.word_count} words
            extracted · {report.fonts.length} font{report.fonts.length !== 1 ? "s" : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
