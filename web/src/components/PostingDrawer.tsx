import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PostingDetail } from "../api/types";
import { relativeAge, sourceLabel, sponsorshipLabel, termRuleLabel } from "../lib/format";
import { GhostChecklist } from "./GhostChecklist";
import { MatchMeter } from "./MatchMeter";
import { PostingBriefPanel } from "./PostingBriefPanel";
import { atMidday, today } from "../lib/dates";
import { TailorPanel } from "./TailorPanel";
import { TermChips } from "./TermChips";

// The full posting: everything needed to decide whether to spend an hour on a
// tailored application, in one centred window.
//
// It opens over the lanes rather than beside them because this is a reading
// surface, not a sidebar — the whole point is to replace opening the job site
// in another tab and scrolling two thousand words for the six facts that
// matter. Those six lead; the original description stays available underneath
// for when the parser missed something.

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
    <div className="fixed inset-0 z-40 flex items-start justify-center p-4 sm:p-8 overflow-y-auto">
      <div
        className="fixed inset-0 bg-navy-900/40 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
      />
      <div className="relative w-full max-w-3xl bg-white rounded-xl border border-navy-200 shadow-lift animate-fade-in my-auto">
        {loading && <div className="p-8 text-sm text-navy-500">Loading…</div>}
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
          <h1 className="text-lg font-700 text-navy-900 leading-tight">{posting.title}</h1>
          <p className="text-sm text-navy-600 mt-0.5">{posting.company_name}</p>
        </div>
        <button onClick={onClose} className="btn-ghost -mr-2 -mt-1 text-navy-500" aria-label="Close">
          ✕
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {posting.term_label ? (
          <span className="chip border-beacon-500/30 text-beacon-600">{posting.term_label}</span>
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
        <p className="text-2xs text-navy-500 -mt-3">
          Term evidence: <span className="text-navy-600 italic">“{posting.term_evidence}”</span>
        </p>
      )}

      <div className="flex gap-2">
        <a href={posting.url} target="_blank" rel="noreferrer" className="btn-primary flex-1">
          Open application ↗
        </a>
        <TrackActions postingId={posting.id} />
      </div>

      {posting.brief && (
        <section className="card p-4 space-y-4 bg-paper border-navy-200">
          <h3 className="text-2xs font-600 uppercase tracking-wider text-navy-600">
            The posting, in facts
          </h3>
          <PostingBriefPanel brief={posting.brief} />
        </section>
      )}

      {posting.match ? (
        <section className="card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-2xs font-600 uppercase tracking-wide text-navy-600">
              Match against your corpus
            </h3>
          </div>
          <MatchMeter match={posting.match} />
          <p className="text-xs text-navy-500">{posting.match.summary}</p>
          <TermChips
            matched={posting.match.matched}
            reword={posting.match.reword}
            gaps={posting.match.gaps}
          />
        </section>
      ) : (
        <section className="card p-4 text-xs text-navy-500">
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
          <h3 className="text-2xs font-600 uppercase tracking-wide text-navy-600 mb-2">
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
            <p className="mt-2 text-2xs text-navy-500">
              ATS: {posting.ats_vendor}
              {posting.ats_job_id && ` · job ${posting.ats_job_id}`}
            </p>
          )}
        </section>
      )}

      {posting.description && (
        <section>
          <h3 className="text-2xs font-600 uppercase tracking-wide text-navy-600 mb-2">
            Description
          </h3>
          <div className="text-xs text-navy-600 whitespace-pre-wrap leading-relaxed max-h-80 overflow-y-auto card p-4">
            {posting.description}
          </div>
        </section>
      )}
    </div>
  );
}

/**
 * The Discover → Track hop. Two buttons rather than one, because saving
 * something to read later and recording that you actually sent it are different
 * facts, and the second one is dated — it seeds every wait-time figure the
 * funnel will later report.
 */
function TrackActions({ postingId }: { postingId: string }) {
  const [state, setState] = useState<"idle" | "saving" | "saved" | "applied">("idle");
  const [error, setError] = useState<string | null>(null);
  // Applications get logged days after they were sent as often as not, and the
  // date is what every wait-time figure on the board is computed from.
  const [on, setOn] = useState(today());

  const run = (event?: "applied") => {
    setState("saving");
    setError(null);
    api
      .trackPosting(postingId, event ? { event_type: event, occurred_at: atMidday(on) } : undefined)
      .then(() => setState(event ? "applied" : "saved"))
      .catch((e) => {
        setError(String(e.message ?? e));
        setState("idle");
      });
  };

  if (state === "saved" || state === "applied") {
    return (
      <span className="btn text-xs text-good border border-good/30 bg-good/5 shrink-0">
        ✓ {state === "applied" ? "Logged as applied" : "On your board"}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-1.5 shrink-0" title={error ?? undefined}>
      <button
        onClick={() => run()}
        disabled={state === "saving"}
        className="btn-toggle text-xs"
        title="Add to your board without marking it applied"
      >
        Save
      </button>
      <button
        onClick={() => run("applied")}
        disabled={state === "saving"}
        className="btn-toggle text-xs"
        title="Record that you applied, on the date shown"
      >
        I applied
      </button>
      <input
        type="date"
        value={on}
        max={today()}
        onChange={(e) => setOn(e.target.value || today())}
        title="The date you applied. Change it when logging something you sent earlier."
        className="text-2xs bg-white border border-navy-200 rounded px-1.5 py-1 text-navy-700
                   hover:border-navy-300 focus:border-beacon-500 outline-none"
      />
    </div>
  );
}
