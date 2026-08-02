import type { TermMatch } from "../api/types";

// The three-bucket keyword display — the actual point of match scoring. Each
// bucket reads differently on purpose:
//   evidenced  the corpus supports this          (calm, confirming)
//   reword     you have it, worded differently    (a nudge, not a warning)
//   gaps       genuinely missing                   (the actionable list)

type Variant = "matched" | "reword" | "gap";

// The rule colour is the only thing distinguishing the three buckets once they
// are on screen together, so each is a different hue rather than a different
// shade: evidenced reads settled, a reword reads like a note, a gap takes the
// beacon because it is the one thing here worth acting on.
const RULE: Record<Variant, string> = {
  matched: "border-good",
  reword: "border-safety",
  gap: "border-beacon-500",
};

function Term({ term, variant, count }: { term: TermMatch; variant: Variant; count?: boolean }) {
  return (
    <span className={`term ${RULE[variant]}`} title={termTooltip(term, variant)}>
      <span>{term.term}</span>
      {count && term.posting_count > 1 && (
        <span className="term-count">×{term.posting_count}</span>
      )}
    </span>
  );
}

function termTooltip(term: TermMatch, variant: Variant): string {
  const base = `"${term.term}" appears ${term.posting_count}× in this posting`;
  if (variant === "matched") return `${base}; ${term.corpus_count}× in your corpus`;
  if (variant === "reword")
    return `${base}. Your corpus covers this as: ${term.component_evidence.join(", ")}`;
  return `${base}; not found in your corpus`;
}

export function TermChips({
  matched,
  reword,
  gaps,
}: {
  matched: TermMatch[];
  reword: TermMatch[];
  gaps: TermMatch[];
}) {
  const hasAny = matched.length || reword.length || gaps.length;
  if (!hasAny) {
    return <p className="text-sm text-navy-500">No comparable terms — add a description or corpus detail.</p>;
  }
  return (
    <div className="space-y-3">
      {matched.length > 0 && (
        <Bucket label="Evidenced" hint="your corpus supports these">
          {matched.map((t) => (
            <Term key={t.term} term={t} variant="matched" />
          ))}
        </Bucket>
      )}
      {reword.length > 0 && (
        <Bucket label="Phrase to mirror" hint="you have this — match their wording">
          {reword.map((t) => (
            <Term key={t.term} term={t} variant="reword" />
          ))}
        </Bucket>
      )}
      {gaps.length > 0 && (
        <Bucket label="Gaps" hint="emphasised here, absent from your corpus">
          {gaps.map((t) => (
            <Term key={t.term} term={t} variant="gap" count />
          ))}
        </Bucket>
      )}
    </div>
  );
}

function Bucket({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline gap-2">
        <span className="text-2xs font-600 uppercase tracking-wider text-navy-600">{label}</span>
        <span className="text-2xs text-navy-400">{hint}</span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">{children}</div>
    </div>
  );
}
