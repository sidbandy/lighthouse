import type { Match } from "../api/types";
import { scoreColor } from "../lib/format";

// The match score, shown as a number *and* an evidence bar, with the honesty
// caveats attached. A high score computed from thin evidence must never look
// the same as a high score from a full description — that distinction is the
// whole reason the backend tracks it.

export function MatchMeter({ match, compact = false }: { match: Match; compact?: boolean }) {
  const { score, thin_evidence, evidence_basis, corpus_size } = match;
  // Against an empty corpus every score is 0, and a 0 is a verdict — "you match
  // nothing" — where the truth is that nothing has been compared. An em dash is
  // the honest glyph for a number that does not exist yet.
  const unscored = corpus_size === 0;
  // A score from thin or title-only evidence must never wear the confident
  // colour: a 100 computed from three terms should read as tentative, not as a
  // perfect match. Muted grey is the honest signal.
  const numberColor = unscored || thin_evidence ? "text-navy-400" : scoreColor(score);
  return (
    <div className="flex items-center gap-2.5">
      <div
        className={`font-mono font-600 tabular-nums ${numberColor} ${compact ? "text-sm" : "text-lg"}`}
        title={unscored ? "Not scored — your corpus is empty" : undefined}
      >
        {unscored ? "—" : score}
      </div>
      <div className="flex-1 min-w-[3rem]">
        <div className="meter">
          <div
            className={`h-full rounded-full transition-all ${
              thin_evidence ? "bg-navy-300" : score >= 45 ? "bg-beacon-500" : "bg-navy-400"
            }`}
            style={{ width: unscored ? "0%" : `${Math.max(score, 2)}%` }}
          />
        </div>
        {!compact && (
          <div className="mt-1 text-2xs text-navy-500 flex items-center gap-1">
            {thin_evidence && <span className="text-warn">⚠</span>}
            <span>{evidence_basis}</span>
          </div>
        )}
      </div>
    </div>
  );
}
