import type { AtsFinding } from "../api/types";

// The findings list. Ranked worst-first, each with the concrete fix. Severity
// is colour-coded so the operator sees at a glance which items actually cause a
// rejection versus which are polish.

const SEVERITY: Record<string, { color: string; ring: string; label: string; mark: string }> = {
  CRITICAL: {
    color: "text-bad",
    ring: "border-bad/30 bg-bad/5",
    label: "Auto-reject risk",
    mark: "✕",
  },
  WARNING: {
    color: "text-warn",
    ring: "border-warn/30 bg-warn/5",
    label: "Degrades the parse",
    mark: "!",
  },
  MINOR: { color: "text-mist-400", ring: "border-ink-700 bg-ink-850", label: "Polish", mark: "•" },
};

export function AtsFindings({ findings }: { findings: AtsFinding[] }) {
  if (findings.length === 0) {
    return (
      <div className="card p-5 text-center">
        <div className="text-good text-2xl mb-1">✓</div>
        <p className="text-sm text-mist-200">Nothing to fix. This resume parses cleanly.</p>
      </div>
    );
  }
  return (
    <div className="space-y-2.5">
      {findings.map((f, i) => {
        const s = SEVERITY[f.severity] ?? SEVERITY.MINOR;
        return (
          <div key={i} className={`card border ${s.ring} p-3.5`}>
            <div className="flex items-start gap-2.5">
              <span className={`${s.color} font-700 mt-0.5`}>{s.mark}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <h4 className="text-sm font-600 text-mist-100">{f.title}</h4>
                  <span className={`text-2xs font-500 ${s.color}`}>{s.label}</span>
                </div>
                <p className="text-xs text-mist-400 mt-1 leading-relaxed">{f.detail}</p>
                {f.evidence && (
                  <div className="mt-2 text-2xs font-mono text-mist-300 bg-ink-950 border border-ink-700 rounded px-2 py-1 overflow-x-auto">
                    {f.evidence}
                  </div>
                )}
                <div className="mt-2 flex items-start gap-1.5 text-xs">
                  <span className="text-beacon-400 font-600 shrink-0">Fix</span>
                  <span className="text-mist-300">{f.fix}</span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
