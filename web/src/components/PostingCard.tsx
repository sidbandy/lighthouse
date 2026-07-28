import type { ScoredPosting } from "../api/types";
import { relativeAge, sponsorshipLabel, termRuleLabel } from "../lib/format";
import { MatchMeter } from "./MatchMeter";

// One posting in a lane. Dense but scannable: the match meter and the top gaps
// are what the operator reads first, so they lead. Everything shown is a fact
// the operator can verify, per the honesty principle.

export function PostingCard({
  posting,
  onOpen,
}: {
  posting: ScoredPosting;
  onOpen: (id: string) => void;
}) {
  const gaps = posting.match.gaps.slice(0, 4);
  const sponsorship = sponsorshipLabel(posting.sponsorship);

  return (
    <button
      onClick={() => onOpen(posting.id)}
      className="card w-full text-left p-3.5 hover:border-ink-600 hover:shadow-lift transition-all
                 duration-150 animate-fade-in group"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-600 text-mist-100 truncate group-hover:text-white">
            {posting.title}
          </div>
          <div className="text-xs text-mist-300 truncate">{posting.company_name}</div>
        </div>
        {!posting.is_active && (
          <span className="chip border-bad/30 text-bad shrink-0">closed</span>
        )}
      </div>

      <div className="mt-2.5">
        <MatchMeter match={posting.match} />
      </div>

      {gaps.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1">
          {gaps.map((g) => (
            <span key={g.term} className="chip border-ink-600 bg-ink-800 text-mist-400 text-2xs">
              {g.is_technical && <span className="text-beacon-400/60">◆</span>}
              {g.term}
            </span>
          ))}
        </div>
      )}

      <div className="mt-2.5 flex items-center gap-1.5 flex-wrap text-2xs text-mist-400">
        {posting.term_label ? (
          <span className="chip">{posting.term_label}</span>
        ) : (
          <span className="chip text-mist-400">term unknown</span>
        )}
        <span className="text-mist-500" title={`term ${termRuleLabel(posting.term_rule)}`}>
          · {termRuleLabel(posting.term_rule)}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {posting.location_labels[0] && <span>{posting.location_labels[0]}</span>}
          <span>· {relativeAge(posting.age_days)}</span>
          {posting.source_count > 1 && (
            <span className="text-mist-300" title={`Seen on ${posting.source_count} lists`}>
              · {posting.source_count} lists
            </span>
          )}
        </span>
      </div>

      {sponsorship && (
        <div className="mt-1.5">
          <span className="chip border-warn/25 bg-warn/5 text-warn/90">{sponsorship}</span>
        </div>
      )}
    </button>
  );
}
