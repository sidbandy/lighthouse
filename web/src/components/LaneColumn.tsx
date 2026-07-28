import type { LaneBucket } from "../api/types";
import { PostingCard } from "./PostingCard";

// One of the three lanes. The header carries the lane's identity and its
// weekly quota, so "apply broadly" reads as a concrete target rather than a
// vague intention.

const LANE_META: Record<
  string,
  { title: string; blurb: string; accent: string; dot: string }
> = {
  reach: {
    title: "Reach",
    blurb: "Selective, or the match is thin. Keep a few alive.",
    accent: "text-reach",
    dot: "bg-reach",
  },
  target: {
    title: "Target",
    blurb: "Realistic match at a realistic bar. The core of the season.",
    accent: "text-target",
    dot: "bg-target",
  },
  safety: {
    title: "Safety",
    blurb: "Strong match, less competitive. Keep the funnel honest.",
    accent: "text-safety",
    dot: "bg-safety",
  },
};

export function LaneColumn({
  bucket,
  onOpen,
}: {
  bucket: LaneBucket;
  onOpen: (id: string) => void;
}) {
  const meta = LANE_META[bucket.lane];
  return (
    <section className="flex flex-col min-w-0">
      <header className="sticky top-0 z-10 bg-ink-950/90 backdrop-blur pb-2.5 pt-1">
        <div className="flex items-baseline gap-2">
          <span className={`h-2 w-2 rounded-full ${meta.dot}`} />
          <h2 className={`text-sm font-700 ${meta.accent}`}>{meta.title}</h2>
          <span className="text-2xs text-mist-400 tabular-nums">{bucket.count} shown</span>
          <span className="ml-auto chip border-ink-700 text-mist-400" title="Suggested weekly applications">
            {bucket.weekly_quota}/week
          </span>
        </div>
        <p className="mt-1 text-2xs text-mist-400 leading-snug">{meta.blurb}</p>
      </header>

      <div className="flex flex-col gap-2.5 mt-1">
        {bucket.postings.length === 0 ? (
          <div className="card p-4 text-xs text-mist-400">Nothing here with the current filters.</div>
        ) : (
          bucket.postings.map((p) => <PostingCard key={p.id} posting={p} onOpen={onOpen} />)
        )}
      </div>
    </section>
  );
}
