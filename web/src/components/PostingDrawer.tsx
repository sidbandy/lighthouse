import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ApplicationEvent, Eligibility, PostingDetail, TrackedState } from "../api/types";
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

export function PostingDrawer({
  id,
  onClose,
  onTrackedChange,
}: {
  id: string | null;
  onClose: () => void;
  /** Fired when the posting's board state changes, so the list behind can
   *  re-render its marker without a manual reload. */
  onTrackedChange?: () => void;
}) {
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
        {posting && (
          <DrawerBody posting={posting} onClose={onClose} onTrackedChange={onTrackedChange} />
        )}
      </div>
    </div>
  );
}

function DrawerBody({
  posting,
  onClose,
  onTrackedChange,
}: {
  posting: PostingDetail;
  onClose: () => void;
  onTrackedChange?: () => void;
}) {
  const sponsorship = sponsorshipLabel(posting.sponsorship);
  const [tracked, setTracked] = useState(posting.tracked);
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
          <>
            <span className="chip border-beacon-500/30 text-beacon-600">{posting.term_label}</span>
            <span className="chip" title="How the cycle was determined">
              {termRuleLabel(posting.term_rule)}
            </span>
          </>
        ) : (
          // One chip, not two: the rule label for an unresolved cycle is also
          // "term unknown", so the pair read as a rendering fault.
          <span className="chip" title="No source stated a cycle, and none could be inferred">
            term unknown
          </span>
        )}
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

      {posting.eligibility && posting.eligibility.verdict !== "not_stated" && (
        <EligibilityNote eligibility={posting.eligibility} />
      )}

      <div className="flex gap-2 items-start">
        <a href={posting.url} target="_blank" rel="noreferrer" className="btn-primary flex-1">
          Open application ↗
        </a>
        <TrackActions
          postingId={posting.id}
          tracked={tracked}
          onChange={(next) => {
            setTracked(next);
            onTrackedChange?.();
          }}
        />
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
 * The graduation-window check, shown only when the posting actually states one.
 *
 * Silent on `not_stated`, which is most postings — an absence rendered as a
 * reassuring green tick would be a claim the posting never made.
 */
function EligibilityNote({ eligibility }: { eligibility: Eligibility }) {
  const blocked = eligibility.verdict === "not_eligible";
  return (
    <section
      className={`card p-3 ${blocked ? "border-bad/30 bg-bad/5" : "border-good/25 bg-good/5"}`}
    >
      <p className={`text-xs font-600 ${blocked ? "text-bad" : "text-good"}`}>
        {eligibility.headline}
      </p>
      <p className="text-2xs text-navy-600 mt-0.5 leading-relaxed">{eligibility.detail}</p>
      {eligibility.evidence && (
        <p className="text-2xs text-navy-500 mt-1 italic">“{eligibility.evidence}”</p>
      )}
    </section>
  );
}

/**
 * The Discover → Track hop, and the answer to "have I already applied to this?"
 *
 * Untracked, it offers two buttons rather than one: saving something to read
 * later and recording that you actually sent it are different facts, and the
 * second is dated — it seeds every wait-time figure the funnel later reports.
 * Tracked, it stops offering to save and shows where the application actually
 * is, with only the transitions that make sense from there.
 */
function TrackActions({
  postingId,
  tracked,
  onChange,
}: {
  postingId: string;
  tracked: TrackedState | null;
  onChange: (next: TrackedState) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Applications get logged days after they were sent as often as not, and the
  // date is what every wait-time figure on the board is computed from.
  const [on, setOn] = useState(today());

  const run = async (event?: ApplicationEvent) => {
    setBusy(true);
    setError(null);
    try {
      const payload = event ? { event_type: event, occurred_at: atMidday(on) } : undefined;
      const application =
        tracked && payload
          ? await api.logEvent(tracked.application_id, payload)
          : await api.trackPosting(postingId, payload);
      onChange({
        application_id: application.id,
        stage: application.stage,
        stage_label: application.stage_label,
        is_live: application.is_live,
        is_terminal: application.is_terminal,
        applied_at: tracked?.applied_at ?? null,
        days_silent: application.days_silent,
        silence_note: application.silence_note,
        next_events: application.next_events,
      });
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const dateInput = (
    <input
      type="date"
      value={on}
      max={today()}
      onChange={(e) => setOn(e.target.value || today())}
      title="When this actually happened. Change it when logging something from last week."
      className="text-2xs bg-white border border-navy-200 rounded px-1.5 py-1 text-navy-700
                 hover:border-navy-300 focus:border-beacon-500 outline-none"
    />
  );

  if (!tracked) {
    return (
      <div className="flex items-center gap-1.5 shrink-0" title={error ?? undefined}>
        <button
          onClick={() => run()}
          disabled={busy}
          className="btn-toggle text-xs"
          title="Add to your board without marking it applied"
        >
          Save
        </button>
        <button
          onClick={() => run("applied")}
          disabled={busy}
          className="btn-toggle text-xs"
          title="Record that you applied, on the date shown"
        >
          I applied
        </button>
        {dateInput}
      </div>
    );
  }

  return (
    <div className="shrink-0 text-right space-y-1" title={error ?? undefined}>
      <div className="flex items-center justify-end gap-1.5">
        <span
          className={`chip ${
            tracked.is_terminal
              ? "text-navy-400"
              : "border-good/30 text-good bg-good/5"
          }`}
        >
          {tracked.is_terminal ? "" : "✓ "}
          {tracked.stage_label}
        </span>
        {tracked.next_events.length > 0 && dateInput}
      </div>
      {tracked.silence_note && (
        <p className="text-2xs text-navy-500">{tracked.silence_note}</p>
      )}
      {tracked.next_events.length > 0 && (
        <div className="flex flex-wrap justify-end gap-1">
          {tracked.next_events.map((t) => (
            <button
              key={t.event_type}
              onClick={() => run(t.event_type)}
              disabled={busy}
              className={`text-2xs px-1.5 py-0.5 rounded transition-colors disabled:opacity-40 ${
                t.is_setback
                  ? "text-navy-400 hover:text-bad hover:bg-bad/5"
                  : "text-navy-600 hover:text-beacon-700 hover:bg-beacon-glow"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
