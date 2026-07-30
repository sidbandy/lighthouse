import { useState } from "react";
import { api } from "../api/client";
import type { Requirement, TailorReport } from "../api/types";

// Per-posting résumé tailoring, inside the posting drawer. Reads the job
// description closely and, against the operator's corpus (and optionally the
// résumé text they paste), shows what's required vs preferred, the knockouts,
// and the honest three buckets — with the specific edit for each.

const TIER_LABEL: Record<string, string> = {
  REQUIRED: "required",
  PREFERRED: "preferred",
  RESPONSIBILITY: "part of the role",
  GENERAL: "mentioned",
};

export function TailorPanel({ postingId }: { postingId: string }) {
  const [report, setReport] = useState<TailorReport | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const run = () => {
    setLoading(true);
    setError(null);
    api
      .tailor(postingId, resumeText.trim() || undefined)
      .then(setReport)
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn-toggle w-full justify-center">
        Tailor my résumé to this posting →
      </button>
    );
  }

  return (
    <section className="card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-2xs font-600 uppercase tracking-wide text-mist-300">
          Tailor to this posting
        </h3>
        {report && <Coverage report={report} />}
      </div>

      <textarea
        value={resumeText}
        onChange={(e) => setResumeText(e.target.value)}
        placeholder="Optional: paste your résumé text to see what's already on it vs. what you have but left off. Without it, this still shows what the posting wants and what your corpus can back."
        className="w-full h-20 text-xs bg-ink-950 border border-ink-700 rounded-lg p-2.5
                   text-mist-200 placeholder:text-mist-500 focus:border-ink-600 outline-none resize-y"
      />
      <button onClick={run} disabled={loading} className="btn-primary w-full">
        {loading ? "Reading the posting…" : report ? "Re-run" : "Analyze fit"}
      </button>

      {error && <p className="text-xs text-bad">{error}</p>}

      {report && (
        <div className="space-y-4 animate-fade-in">
          <p className="text-xs text-mist-300 leading-relaxed">{report.summary}</p>

          {report.hard_requirements.length > 0 && (
            <Group title="Knockouts — check you clear these" tone="warn">
              {report.hard_requirements.map((h) => (
                <div key={h.kind} className="text-xs text-mist-300">
                  <span className="text-warn font-600">{h.label}:</span>{" "}
                  <span className="text-mist-400 italic">“{h.detail}”</span>
                </div>
              ))}
            </Group>
          )}

          {report.missing_from_resume.length > 0 && (
            <ReqGroup
              title="Quick wins — you have these, add them"
              hint="on your corpus but not the résumé you pasted"
              items={report.missing_from_resume}
              tone="good"
            />
          )}
          {report.rewords.length > 0 && (
            <ReqGroup
              title="Reword to match theirs"
              hint="you have the experience, mirror their exact term"
              items={report.rewords}
              tone="reword"
            />
          )}
          {report.required_gaps.length > 0 && (
            <ReqGroup
              title="Required, and you can't back it"
              hint="real gaps on must-haves — decide honestly"
              items={report.required_gaps}
              tone="bad"
            />
          )}
          {report.evidenced.length > 0 && (
            <ReqGroup
              title="Already covered"
              hint="the posting wants these and your corpus has them"
              items={report.evidenced.slice(0, 12)}
              tone="good"
              compact
            />
          )}
          {report.other_gaps.length > 0 && (
            <ReqGroup
              title="Preferred / nice-to-have gaps"
              hint="lower risk — not required"
              items={report.other_gaps.slice(0, 10)}
              tone="neutral"
              compact
            />
          )}
        </div>
      )}
    </section>
  );
}

function Coverage({ report }: { report: TailorReport }) {
  const { coverage, potential_coverage } = report;
  return (
    <div className="text-right" title="Weighted share of the posting's requirements your corpus can evidence">
      <span className="font-mono font-600 text-beacon-400 tabular-nums">{coverage}%</span>
      {potential_coverage > coverage && (
        <span className="text-2xs text-mist-400"> → {potential_coverage}% with edits</span>
      )}
    </div>
  );
}

const TONE_CHIP: Record<string, string> = {
  good: "border-good/30 bg-good/5 text-good/90",
  reword: "border-safety/30 bg-safety/5 text-safety/90",
  bad: "border-bad/30 bg-bad/5 text-bad/90",
  neutral: "border-ink-600 bg-ink-800 text-mist-300",
};

function ReqGroup({
  title,
  hint,
  items,
  tone,
  compact = false,
}: {
  title: string;
  hint: string;
  items: Requirement[];
  tone: keyof typeof TONE_CHIP;
  compact?: boolean;
}) {
  return (
    <Group title={title} hint={hint}>
      {compact ? (
        <div className="flex flex-wrap gap-1.5">
          {items.map((r) => (
            <span key={r.term} className={`chip ${TONE_CHIP[tone]}`} title={r.advice}>
              {r.is_technical && <span className="opacity-60">◆</span>}
              {r.term}
              {r.tier === "REQUIRED" && <span className="opacity-70 text-2xs">req</span>}
            </span>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((r) => (
            <div key={r.term} className="text-xs">
              <div className="flex items-baseline gap-1.5">
                <span className={`chip ${TONE_CHIP[tone]}`}>{r.term}</span>
                <span className="text-2xs text-mist-500">
                  {TIER_LABEL[r.tier]} · seen {r.posting_count}×
                </span>
              </div>
              <p className="text-mist-400 mt-1 leading-snug">{r.advice}</p>
            </div>
          ))}
        </div>
      )}
    </Group>
  );
}

function Group({
  title,
  hint,
  tone,
  children,
}: {
  title: string;
  hint?: string;
  tone?: "warn";
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5">
        <span className={`text-2xs font-600 ${tone === "warn" ? "text-warn" : "text-mist-200"}`}>
          {title}
        </span>
        {hint && <span className="text-2xs text-mist-500"> · {hint}</span>}
      </div>
      {children}
    </div>
  );
}
