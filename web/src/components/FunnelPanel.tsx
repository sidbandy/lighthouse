import type { Funnel } from "../api/types";

// The funnel. Every figure is a count of things that happened, and the sample
// it came from is printed underneath.
//
// What this deliberately does not show: an interview rate from nine
// applications, an expected wait, or any number that would let the operator
// believe the tool knows something it doesn't. Below the backend's MIN_SAMPLE
// the conversion rows say so in words instead of showing a percentage — a
// student with two interviews out of nine does not have a "22% interview rate",
// and printing one would be inventing precision from noise.

export function FunnelPanel({ funnel }: { funnel: Funnel }) {
  if (funnel.total === 0) return null;

  const applied = funnel.stages.find((s) => s.stage === "APPLIED")?.reached ?? 0;

  return (
    <section className="card p-4 space-y-4">
      <div>
        <h2 className="text-sm font-600 text-navy-900">Your funnel so far</h2>
        <p className="text-2xs text-navy-500 mt-0.5">{funnel.basis}</p>
      </div>

      {/* Stage counts. Bars are scaled against the applied count, so the shape
          is comparable across stages without implying a rate. */}
      <div className="space-y-1.5">
        {funnel.stages.map((s) => (
          <div key={s.stage} className="flex items-center gap-3">
            <span className="text-2xs text-navy-500 w-24 shrink-0">{s.label}</span>
            <div className="flex-1 h-4 bg-navy-50 rounded-sm overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  s.stage === "REJECTED" ? "bg-navy-200" : "bg-beacon-500/70"
                }`}
                style={{ width: applied ? `${Math.min(100, (s.reached / applied) * 100)}%` : "0%" }}
              />
            </div>
            <span className="text-xs font-mono tabular-nums text-navy-800 w-8 text-right shrink-0">
              {s.reached}
            </span>
            {s.current > 0 && (
              <span
                className="text-2xs text-navy-400 w-16 shrink-0"
                title={`${s.current} sitting at this stage right now`}
              >
                {s.current} now
              </span>
            )}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 pt-1">
        <div>
          <h3 className="rule-label mb-1.5">Of everything you applied to</h3>
          <ul className="space-y-1">
            {funnel.conversions.map((c) => (
              <li key={c.to_label} className="text-2xs flex items-baseline justify-between gap-2">
                <span className="text-navy-500">{c.to_label}</span>
                <span
                  className={
                    c.has_enough_data
                      ? "text-navy-800 font-600 tabular-nums"
                      : "text-navy-400 text-right"
                  }
                >
                  {c.statement}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="rule-label mb-1.5">How long it took</h3>
          <ul className="space-y-1">
            {funnel.waits.map((w) => (
              <li key={w.to_label} className="text-2xs flex items-baseline justify-between gap-2">
                <span className="text-navy-500">
                  {w.from_label} → {w.to_label}
                </span>
                <span
                  className={
                    w.sample_size > 0 ? "text-navy-800 tabular-nums text-right" : "text-navy-400"
                  }
                >
                  {w.statement}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
