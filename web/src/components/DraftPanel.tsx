import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Contact, Draft, InteractionKind } from "../api/types";

// Two drafts to choose between, and the trace behind them.
//
// Lighthouse does not send anything. The draft is copied out, edited, and sent
// by the operator from their own account — automated outbound to real people is
// a reputation risk with no upside for one person running one search.
//
// The provenance line is not decoration. Every claim in the message traces to a
// corpus fact, and if the grounding check found a figure the corpus does not
// support, the model's version is discarded and the deterministic one shown
// instead. Sending a number you cannot defend is the specific failure this
// guards against, because you will be asked about it on a call.

const KIND_LABELS: Record<string, string> = {
  cold_outreach: "First message",
  follow_up: "Follow-up",
  thank_you: "Thank-you",
  update: "Update",
  reply: "Reply",
};

const LOG_AS: Record<string, InteractionKind> = {
  cold_outreach: "outreach",
  follow_up: "outreach",
  thank_you: "thank_you",
  update: "outreach",
  reply: "outreach",
};

export function DraftPanel({
  contact,
  kind,
  onClose,
  onLogged,
}: {
  contact: Contact;
  kind: string;
  onClose: () => void;
  onLogged: (kind: InteractionKind) => void;
}) {
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    api
      .draftMessages(contact.id, kind)
      .then(setDrafts)
      .catch((e) => setError(String((e as Error).message ?? e)));
  }, [contact.id, kind]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const copy = async (draft: Draft) => {
    await navigator.clipboard.writeText(`${draft.subject}\n\n${draft.body}`);
    setCopied(draft.variant);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center p-4 sm:p-8 overflow-y-auto">
      <div className="fixed inset-0 bg-navy-900/40 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div className="relative w-full max-w-3xl bg-white rounded-xl border border-navy-200 shadow-lift animate-fade-in my-auto p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-700 text-navy-900 leading-tight">
              {KIND_LABELS[kind] ?? "Draft"} to {contact.name}
            </h1>
            <p className="text-2xs text-navy-500 mt-0.5">
              {[contact.role_title, contact.company_name].filter(Boolean).join(" · ")} · Lighthouse
              never sends anything — copy it, edit it, send it yourself.
            </p>
          </div>
          <button onClick={onClose} className="btn-ghost -mr-2 -mt-1 text-navy-500" aria-label="Close">
            ✕
          </button>
        </div>

        {error && (
          <div className="card p-3 border-bad/30 bg-bad/5">
            <p className="text-xs text-bad leading-relaxed">{error}</p>
          </div>
        )}

        {!drafts && !error && <p className="text-xs text-navy-500">Writing…</p>}

        {drafts?.map((draft) => (
          <section key={draft.variant} className="card p-4 space-y-2 bg-paper border-navy-200">
            <div className="flex items-baseline justify-between gap-2 flex-wrap">
              <h2 className="text-2xs font-600 uppercase tracking-wide text-navy-600">
                {draft.variant}
              </h2>
              <span className="text-2xs text-navy-400 tabular-nums">
                {draft.word_count} words
                {draft.is_fallback && " · template"}
              </span>
            </div>

            <p className="text-xs text-navy-500">
              <span className="text-navy-400">Subject: </span>
              {draft.subject}
            </p>
            <div className="text-xs text-navy-800 whitespace-pre-wrap leading-relaxed bg-white rounded-lg border border-navy-200 p-3">
              {draft.body}
            </div>

            {draft.warnings.map((w) => (
              <p key={w} className="text-2xs text-warn leading-relaxed">
                ⚠ {w}
              </p>
            ))}

            <p className="text-2xs text-navy-400 leading-relaxed">
              Built from {draft.source_fact_ids.length} corpus fact
              {draft.source_fact_ids.length !== 1 ? "s" : ""}. {draft.grounding_note}
            </p>

            <div className="flex items-center gap-2 pt-0.5">
              <button onClick={() => copy(draft)} className="btn-toggle text-xs">
                {copied === draft.variant ? "✓ Copied" : "Copy"}
              </button>
            </div>
          </section>
        ))}

        {drafts && drafts.length > 0 && (
          <div className="flex items-center gap-2 pt-1 border-t border-navy-100">
            <button
              onClick={() => onLogged(LOG_AS[kind] ?? "outreach")}
              className="btn-primary text-xs"
            >
              I sent one — log it
            </button>
            <span className="text-2xs text-navy-400">
              Dates the message, which is what the follow-up clock runs on.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
