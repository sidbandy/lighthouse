import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SourceHealth } from "../api/types";
import { sourceLabel } from "../lib/format";

// Which feeds are working, and which quietly stopped.
//
// The masthead has always said "15 need attention" and there was no way to find
// out which fifteen. A count you cannot act on is worse than no count: it reads
// as a problem you are ignoring rather than one you can fix, and after a week
// you stop seeing it.
//
// Two failure modes are shown apart because they mean different things. A
// quarantined source returned less than half its previous rows, so the parse
// probably broke and the prior data is deliberately being kept. A failing source
// could not be reached at all — usually a board slug that changed or a company
// that took its board down, which is a one-line fix in the seed list.

export function SourcePanel({ onClose }: { onClose: () => void }) {
  const [health, setHealth] = useState<SourceHealth[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    api.sourceHealth().then(setHealth).catch(() => setHealth([]));
    api.sourceBreakdown().then(setCounts).catch(() => {});
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const quarantined = (health ?? []).filter((s) => s.is_quarantined);
  const failing = (health ?? []).filter((s) => !s.is_quarantined && s.last_error);
  const healthy = (health ?? []).filter((s) => s.last_success_at && !s.is_quarantined && !s.last_error);

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center p-4 sm:p-8 overflow-y-auto">
      <div className="fixed inset-0 bg-navy-900/40 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div className="relative w-full max-w-2xl bg-white rounded-xl border border-navy-200 shadow-lift animate-fade-in my-auto p-6 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-700 text-navy-900 leading-tight">Sources</h1>
            <p className="text-sm text-navy-500 mt-0.5">
              Feeds rot. This is what makes that visible instead of silent — a list that
              quietly stops updating still looks like a list.
            </p>
          </div>
          <button onClick={onClose} className="btn-ghost -mr-2 -mt-1 text-navy-500" aria-label="Close">
            ✕
          </button>
        </div>

        {health === null && <p className="text-xs text-navy-500">Loading…</p>}

        {health !== null && (
          <>
            <Group
              title="Parse looks broken"
              blurb="Returned less than half its previous rows, so the prior postings were kept rather than replaced. Usually the source changed its layout."
              sources={quarantined}
              counts={counts}
              tone="bad"
            />
            <Group
              title="Could not be reached"
              blurb="The fetch failed outright. For an ATS board that is normally a slug that changed or a company that took its board down."
              sources={failing}
              counts={counts}
              tone="warn"
            />
            <Group
              title="Healthy"
              blurb=""
              sources={healthy}
              counts={counts}
              tone="good"
              collapsed
            />
          </>
        )}
      </div>
    </div>
  );
}

function Group({
  title,
  blurb,
  sources,
  counts,
  tone,
  collapsed = false,
}: {
  title: string;
  blurb: string;
  sources: SourceHealth[];
  counts: Record<string, number>;
  tone: "good" | "warn" | "bad";
  collapsed?: boolean;
}) {
  const [open, setOpen] = useState(!collapsed);
  if (sources.length === 0) return null;

  const colour = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "text-navy-600";

  return (
    <section>
      <button onClick={() => setOpen((v) => !v)} className="w-full text-left">
        <h2 className="rule-label">
          <span className={colour}>
            {title} · {sources.length}
          </span>
        </h2>
      </button>
      {blurb && open && (
        <p className="text-2xs text-navy-400 mt-1 leading-relaxed max-w-xl">{blurb}</p>
      )}
      {open && (
        <ul className="mt-2 space-y-1">
          {sources.map((s) => (
            <li key={s.source_id} className="flex items-baseline gap-2 text-2xs">
              <span className="text-navy-700 truncate">{sourceLabel(s.source_id)}</span>
              <span className="text-navy-400 tabular-nums shrink-0">
                {counts[s.source_id] ?? 0} live
              </span>
              {s.consecutive_failures > 0 && (
                <span className="text-navy-400 shrink-0">
                  {s.consecutive_failures} fail{s.consecutive_failures !== 1 ? "s" : ""}
                </span>
              )}
              {s.last_error && (
                <span className="text-navy-400 truncate italic" title={s.last_error}>
                  {s.last_error.replace(/^[\w.]+: /, "")}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
