import type { ParsePreview as Preview } from "../api/types";

// The single most convincing thing in the resume checker: what the operator
// laid out, next to what a naive ATS actually extracts. When the two disagree,
// the scramble is right there on screen — no need to take our word for it.

export function ParsePreview({ preview }: { preview: Preview }) {
  if (preview.column_count <= 1 && !preview.scrambled) {
    return (
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-good">✓</span>
          <h3 className="text-sm font-600 text-navy-900">Reading order is clean</h3>
        </div>
        <p className="text-xs text-navy-500 mb-3">
          A single-column layout. The ATS reads it top-to-bottom, exactly as you wrote it.
        </p>
        <ExtractBlock text={preview.ats_text} tone="good" />
      </div>
    );
  }

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-bad">⚠</span>
        <h3 className="text-sm font-600 text-navy-900">
          {preview.scrambled ? "The parser scrambles your layout" : "Multi-column layout"}
        </h3>
      </div>
      <p className="text-xs text-navy-500 mb-3">
        Your resume has {preview.column_count} columns. Systems like Workday read straight across
        the page. The right side is the order the recruiter's system actually receives — notice how
        the columns interleave.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <Label>What you laid out</Label>
          <ExtractBlock text={preview.visual_text} tone="neutral" />
        </div>
        <div>
          <Label tone="bad">What the ATS extracts</Label>
          <ExtractBlock text={preview.ats_text} tone="bad" />
        </div>
      </div>
    </div>
  );
}

function Label({ children, tone }: { children: React.ReactNode; tone?: "bad" }) {
  return (
    <div
      className={`text-2xs font-600 uppercase tracking-wide mb-1 ${
        tone === "bad" ? "text-bad/90" : "text-navy-500"
      }`}
    >
      {children}
    </div>
  );
}

function ExtractBlock({ text, tone }: { text: string; tone: "good" | "neutral" | "bad" }) {
  const border =
    tone === "bad" ? "border-bad/25" : tone === "good" ? "border-good/20" : "border-navy-200";
  return (
    <pre
      className={`text-2xs font-mono leading-relaxed text-navy-600 whitespace-pre-wrap
                  bg-paper border ${border} rounded-lg p-3 max-h-72 overflow-y-auto`}
    >
      {text || "(no text extracted)"}
    </pre>
  );
}
