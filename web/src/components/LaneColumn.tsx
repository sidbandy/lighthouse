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
      {/* The lane's colour is carried by a rule across the top of the column
          rather than a dot beside the title — at a glance you read three
          columns, not three bullets. */}
      <header className="sticky top-0 z-10 bg-paper/95 backdrop-blur pb-2.5">
        <div className={`h-0.5 w-full rounded-full ${meta.dot}`} />
        <div className="flex items-baseline gap-2 mt-2">
          <h2 className={`text-sm font-700 ${meta.accent}`}>{meta.title}</h2>
          <span className="text-2xs text-navy-400 tabular-nums">{bucket.count} shown</span>
          <span
            className="ml-auto text-2xs text-navy-400 tabular-nums"
            title="Suggested weekly applications for this lane"
          >
            {bucket.weekly_quota}/week
          </span>
        </div>
        <p className="mt-0.5 text-2xs text-navy-400 leading-snug">{meta.blurb}</p>
      </header>

      <div className="flex flex-col gap-2.5 mt-1">
        {bucket.postings.length === 0 ? (
          // An empty lane is real information — often that the corpus is too
          // thin to place anything here — but it is not a result, so it does
          // not get a result's weight.
          <div className="rounded-xl border border-dashed border-navy-200 p-4 text-xs text-navy-400">
            Nothing here with the current filters.
          </div>
        ) : (
          bucket.postings.map((p) => <PostingCard key={p.id} posting={p} onOpen={onOpen} />)
        )}
      </div>
    </section>
  );
}
