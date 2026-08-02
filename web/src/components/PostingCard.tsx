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
      className="card w-full text-left p-3.5 hover:border-navy-300 hover:shadow-lift transition-all
                 duration-150 animate-fade-in group"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-600 text-navy-900 truncate group-hover:text-beacon-700 transition-colors">
            {posting.title}
          </div>
          <div className="text-xs text-navy-500 truncate">{posting.company_name}</div>
        </div>
        {!posting.is_active && (
          <span className="text-2xs font-600 uppercase tracking-wide text-bad shrink-0">closed</span>
        )}
      </div>

      <div className="mt-2.5">
        <MatchMeter match={posting.match} />
      </div>

      {gaps.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1">
          {gaps.map((g) => (
            <span key={g.term} className="term border-beacon-500 text-navy-600">
              {g.term}
            </span>
          ))}
        </div>
      )}

      {/* Metadata sits on one hairline-separated line: it is context for the
          decision above it, not another set of things to look at. */}
      <div className="mt-3 pt-2 border-t border-navy-100 flex items-center gap-2 flex-wrap text-2xs text-navy-400">
        <span
          className={posting.term_label ? "font-600 text-navy-600" : "italic"}
          title={`term ${termRuleLabel(posting.term_rule)}`}
        >
          {posting.term_label ?? "term unknown"}
        </span>
        <span>{termRuleLabel(posting.term_rule)}</span>
        {sponsorship && <span className="text-warn">{sponsorship}</span>}
        <span className="ml-auto flex items-center gap-2">
          {posting.location_labels[0] && <span>{posting.location_labels[0]}</span>}
          <span>{relativeAge(posting.age_days)}</span>
          {posting.source_count > 1 && (
            <span className="text-navy-600" title={`Seen on ${posting.source_count} lists`}>
              {posting.source_count} lists
            </span>
          )}
        </span>
      </div>
    </button>
  );
}
