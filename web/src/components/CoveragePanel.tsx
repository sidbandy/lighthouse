import type { Coverage, RoleFamily } from "../api/types";
import { roleLabel } from "../lib/format";
import { ROLES } from "./FilterBar";

// The corpus measured against the postings actually ingested.
//
// Every figure here is a count over a stated sample, and the sample is printed
// underneath. That's the difference between "you cover 61% of the market" —
// which would be a number pretending to be a measurement — and "your facts are
// mentioned in 258 of 425 postings that carry a description", which the operator
// can go and check.

export function CoveragePanel({
  coverage,
  roleFilter,
  onRoleFilter,
}: {
  coverage: Coverage;
  roleFilter: RoleFamily | null;
  onRoleFilter: (role: RoleFamily | null) => void;
}) {
  const { sample_size, reached, unreached, gaps, is_meaningful } = coverage;

  return (
    <section className="card p-4 space-y-4">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-sm font-600 text-mist-100">What your corpus is worth right now</h2>
          <p className="text-2xs text-mist-400 mt-0.5">{coverage.basis}</p>
        </div>
        <div className="flex items-center gap-1 flex-wrap justify-end">
          <span className="text-2xs text-mist-500 mr-1">measure against</span>
          <button
            onClick={() => onRoleFilter(null)}
            className={roleFilter === null ? "btn-toggle-on text-2xs" : "btn-toggle text-2xs"}
          >
            All roles
          </button>
          {ROLES.map((r) => (
            <button
              key={r}
              onClick={() => onRoleFilter(r)}
              className={roleFilter === r ? "btn-toggle-on text-2xs" : "btn-toggle text-2xs"}
            >
              {roleLabel(r)}
            </button>
          ))}
        </div>
      </div>

      {sample_size === 0 ? (
        <p className="text-xs text-mist-400">
          No postings with full descriptions have been ingested yet, so there is nothing to measure
          against. Run an ingest and this fills in.
        </p>
      ) : (
        <>
          <div>
            <div className="flex items-baseline gap-2 mb-1.5">
              <span className="font-mono text-xl font-600 text-mist-100 tabular-nums">
                {reached}
              </span>
              <span className="text-xs text-mist-400">
                of {sample_size} sampled postings mention at least one term you can evidence
              </span>
            </div>
            <div className="meter">
              <div
                className="h-full bg-beacon-500/70 rounded-full transition-all duration-500"
                style={{ width: `${sample_size ? (reached / sample_size) * 100 : 0}%` }}
              />
            </div>
            <p className="text-2xs text-mist-500 mt-1.5">
              {unreached} mention nothing your corpus covers. A term counted here appears in the
              posting — it is not a claim that you'd be a strong candidate.
            </p>
          </div>

          {!is_meaningful && (
            <p className="text-2xs text-warn">
              Small sample — these counts move a lot with each ingest. Treat them as indicative.
            </p>
          )}

          {gaps.length > 0 && (
            <div>
              <h3 className="text-2xs font-600 uppercase tracking-wide text-mist-300 mb-1">
                Most asked for, and nothing in your corpus evidences it
              </h3>
              <p className="text-2xs text-mist-500 mb-2">
                These are real gaps, not keywords to add. Putting a term on your résumé you can't
                defend is how you fail the interview instead of the filter.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {gaps.map((g) => (
                  <span
                    key={g.term}
                    className="chip border-ink-600 bg-ink-800 text-mist-300"
                    title={`Appears in ${g.posting_count} of ${sample_size} sampled postings${
                      g.core_count > 0 ? `, central to ${g.core_count}` : ""
                    }`}
                  >
                    {g.is_technical && <span className="opacity-50">◆</span>}
                    {g.term}
                    <span className="text-mist-500 tabular-nums">{g.posting_count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
