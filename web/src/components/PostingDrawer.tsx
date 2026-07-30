import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PostingDetail } from "../api/types";
import { relativeAge, sourceLabel, sponsorshipLabel, termRuleLabel } from "../lib/format";
import { GhostChecklist } from "./GhostChecklist";
import { MatchMeter } from "./MatchMeter";
import { TailorPanel } from "./TailorPanel";
import { TermChips } from "./TermChips";

// The full posting: everything the operator needs to decide whether to spend an
// hour on a tailored application. Slides in over the lanes.

export function PostingDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const [posting, setPosting] = useState<PostingDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setPosting(null);
    setError(null);
    setLoading(true);
    api
      .posting(id)
      .then(setPosting)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!id) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div className="relative w-full max-w-xl bg-ink-950 border-l border-ink-700 shadow-lift overflow-y-auto animate-fade-in">
        {loading && <div className="p-8 text-sm text-mist-400">Loading…</div>}
        {error && <div className="p-8 text-sm text-bad">Could not load posting. {error}</div>}
        {posting && <DrawerBody posting={posting} onClose={onClose} />}
      </div>
    </div>
  );
}

function DrawerBody({ posting, onClose }: { posting: PostingDetail; onClose: () => void }) {
  const sponsorship = sponsorshipLabel(posting.sponsorship);
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-lg font-700 text-mist-100 leading-tight">{posting.title}</h1>
          <p className="text-sm text-mist-300 mt-0.5">{posting.company_name}</p>
        </div>
        <button onClick={onClose} className="btn-ghost -mr-2 -mt-1 text-mist-400" aria-label="Close">
          ✕
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {posting.term_label ? (
          <span className="chip border-beacon-500/30 text-beacon-400">{posting.term_label}</span>
        ) : (
          <span className="chip">term unknown</span>
        )}
        <span className="chip" title="How the cycle was determined">
          {termRuleLabel(posting.term_rule)}
        </span>
        {posting.location_labels.map((l) => (
          <span key={l} className="chip">
            {l}
          </span>
        ))}
        {sponsorship && <span className="chip border-warn/25 text-warn/90">{sponsorship}</span>}
        <span className="chip">{relativeAge(posting.age_days)}</span>
      </div>

      {posting.term_evidence && (
        <p className="text-2xs text-mist-400 -mt-3">
          Term evidence: <span className="text-mist-300 italic">“{posting.term_evidence}”</span>
        </p>
      )}

      <a href={posting.url} target="_blank" rel="noreferrer" className="btn-primary w-full">
        Open application ↗
      </a>

      {posting.match ? (
        <section className="card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-2xs font-600 uppercase tracking-wide text-mist-300">
              Match against your corpus
            </h3>
          </div>
          <MatchMeter match={posting.match} />
          <p className="text-xs text-mist-400">{posting.match.summary}</p>
          <TermChips
            matched={posting.match.matched}
            reword={posting.match.reword}
            gaps={posting.match.gaps}
          />
        </section>
      ) : (
        <section className="card p-4 text-xs text-mist-400">
          Add a few corpus facts to see how this posting matches your background.
        </section>
      )}

      {posting.description_available && <TailorPanel postingId={posting.id} />}

      {posting.ghost && (
        <section className="card p-4">
          <GhostChecklist ghost={posting.ghost} />
        </section>
      )}

      {posting.sources.length > 0 && (
        <section>
          <h3 className="text-2xs font-600 uppercase tracking-wide text-mist-300 mb-2">
            Seen on {posting.sources.length} {posting.sources.length === 1 ? "source" : "sources"}
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {posting.sources.map((s) => (
              <span key={s.source_id} className="chip">
                {sourceLabel(s.source_id)}
              </span>
            ))}
          </div>
          {posting.ats_vendor && (
            <p className="mt-2 text-2xs text-mist-400">
              ATS: {posting.ats_vendor}
              {posting.ats_job_id && ` · job ${posting.ats_job_id}`}
            </p>
          )}
        </section>
      )}

      {posting.description && (
        <section>
          <h3 className="text-2xs font-600 uppercase tracking-wide text-mist-300 mb-2">
            Description
          </h3>
          <div className="text-xs text-mist-300 whitespace-pre-wrap leading-relaxed max-h-80 overflow-y-auto card p-4">
            {posting.description}
          </div>
        </section>
      )}
    </div>
  );
}
