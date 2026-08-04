import type { BriefFact, PostingBrief } from "../api/types";

// The facts a job description buries, pulled to the top.
//
// Two rules hold this together. Nothing is estimated — a posting that does not
// state its pay shows no pay, because a plausible guess is still a fabrication.
// And every value carries the sentence it came from as a tooltip, so when the
// parser is wrong the operator can see that in one hover rather than acting on
// it.

const ORDER = ["compensation", "arrangement", "duration", "deadline", "gpa"];

export function PostingBriefPanel({ brief }: { brief: PostingBrief }) {
  const { logistics, process, responsibilities, is_thin } = brief;

  if (is_thin && responsibilities.length === 0) {
    return (
      <p className="text-xs text-navy-400">
        This description states no pay, dates, working pattern or interview process. That is
        itself worth knowing — you would be applying without any of it.
      </p>
    );
  }

  const sorted = [...logistics].sort(
    (a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind),
  );

  return (
    <div className="space-y-4">
      {sorted.length > 0 && (
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-3">
          {sorted.map((fact) => (
            <FactCell key={fact.kind} fact={fact} />
          ))}
        </dl>
      )}

      {process.length > 0 && (
        <div>
          <h4 className="rule-label mb-1.5">Interview process, as stated</h4>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {process.map((step) => (
              <span key={step.label} className="term border-safety" title={step.evidence}>
                {step.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {responsibilities.length > 0 && (
        <div>
          <h4 className="rule-label mb-1.5">What you'd actually be doing</h4>
          <ul className="space-y-1">
            {responsibilities.map((line, i) => (
              <li key={i} className="text-xs text-navy-600 leading-relaxed flex gap-2">
                <span className="text-beacon-500 shrink-0">·</span>
                {line}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function FactCell({ fact }: { fact: BriefFact }) {
  // Pay is the number everyone scrolls for, so it gets the beacon and nothing
  // else does. If everything is emphasised, nothing is.
  const isPay = fact.kind === "compensation";
  return (
    <div title={fact.evidence}>
      <dt className="text-2xs uppercase tracking-wider text-navy-400">{fact.label}</dt>
      <dd
        className={`mt-0.5 tabular-nums ${
          isPay ? "text-sm font-600 text-beacon-700" : "text-xs font-500 text-navy-800"
        }`}
      >
        {fact.value}
      </dd>
    </div>
  );
}
