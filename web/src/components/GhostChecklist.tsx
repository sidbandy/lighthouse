import type { GhostAssessment } from "../api/types";

// The ghost-job signal checklist. A list of checked facts, never a probability.
// The label is derived from the signals shown right below it, so the operator
// can always reconstruct the conclusion.

const VERDICT_STYLE: Record<string, { mark: string; color: string }> = {
  good: { mark: "✓", color: "text-good" },
  neutral: { mark: "•", color: "text-navy-500" },
  concern: { mark: "!", color: "text-warn" },
  unknown: { mark: "?", color: "text-navy-400" },
};

const LABEL_TEXT: Record<string, string> = {
  likely_active: "Likely active",
  probably_fine: "Probably fine",
  questionable: "Questionable",
  likely_stale: "Likely stale",
  insufficient_data: "Not enough data",
};

export function GhostChecklist({ ghost }: { ghost: GhostAssessment }) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-2xs font-600 uppercase tracking-wide text-navy-600">Is it live?</h3>
        <span className="text-xs text-navy-800">
          {LABEL_TEXT[ghost.label] ?? ghost.label}{" "}
          <span className="text-navy-500">· {ghost.summary}</span>
        </span>
      </div>
      <ul className="space-y-1.5">
        {ghost.signals.map((s) => {
          const v = VERDICT_STYLE[s.verdict] ?? VERDICT_STYLE.unknown;
          return (
            <li key={s.name} className="flex gap-2 text-xs">
              <span className={`${v.color} font-600 w-3 shrink-0 text-center`}>{v.mark}</span>
              <span className="text-navy-500">
                <span className="text-navy-600">{s.name}:</span> {s.detail}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
