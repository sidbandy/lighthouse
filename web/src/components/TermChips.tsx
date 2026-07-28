import type { TermMatch } from "../api/types";

// The three-bucket keyword display — the actual point of match scoring. Each
// bucket reads differently on purpose:
//   evidenced  the corpus supports this          (calm, confirming)
//   reword     you have it, worded differently    (a nudge, not a warning)
//   gaps       genuinely missing                   (the actionable list)

type Variant = "matched" | "reword" | "gap";

const STYLES: Record<Variant, string> = {
  matched: "border-good/30 bg-good/5 text-good/90",
  reword: "border-safety/30 bg-safety/5 text-safety/90",
  gap: "border-ink-600 bg-ink-800 text-mist-300",
};

function Chip({ term, variant, count }: { term: TermMatch; variant: Variant; count?: boolean }) {
  return (
    <span className={`chip ${STYLES[variant]}`} title={termTooltip(term, variant)}>
      {variant === "matched" && <span className="text-good">✓</span>}
      {term.is_technical && variant === "gap" && <span className="text-beacon-400/70">◆</span>}
      <span>{term.term}</span>
      {count && term.posting_count > 1 && (
        <span className="text-mist-400 tabular-nums">×{term.posting_count}</span>
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
    return <p className="text-sm text-mist-400">No comparable terms — add a description or corpus detail.</p>;
  }
  return (
    <div className="space-y-3">
      {matched.length > 0 && (
        <Bucket label="Evidenced" hint="your corpus supports these">
          {matched.map((t) => (
            <Chip key={t.term} term={t} variant="matched" />
          ))}
        </Bucket>
      )}
      {reword.length > 0 && (
        <Bucket label="Phrase to mirror" hint="you have this — match their wording">
          {reword.map((t) => (
            <Chip key={t.term} term={t} variant="reword" />
          ))}
        </Bucket>
      )}
      {gaps.length > 0 && (
        <Bucket label="Gaps" hint="emphasised here, absent from your corpus">
          {gaps.map((t) => (
            <Chip key={t.term} term={t} variant="gap" count />
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
        <span className="text-2xs font-600 uppercase tracking-wide text-mist-300">{label}</span>
        <span className="text-2xs text-mist-400">{hint}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}
