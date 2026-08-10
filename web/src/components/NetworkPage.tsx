import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  Contact,
  InteractionKind,
  NetworkOverview,
  ReferralReport,
} from "../api/types";
import { atMidday, today } from "../lib/dates";
import { ContactPaste } from "./ContactPaste";
import { DraftPanel } from "./DraftPanel";

// Networking: who you know, who you don't, and what to send next.
//
// The page leads with what is *due* rather than with the contact list, because
// the list is not the work. Finding names was never the hard part — writing
// fifteen non-generic messages and remembering to follow up on all of them is,
// and only one of those is something a person should be holding in their head.
//
// Second is where the network is thin: target companies with nobody at them.
// That is the list an hour on LinkedIn's alumni page can actually change, so it
// is the one worth putting in front of someone.

const LOGGABLE: { kind: InteractionKind; label: string; hint: string }[] = [
  { kind: "outreach", label: "Sent a message", hint: "Starts the follow-up clock" },
  { kind: "reply", label: "They replied", hint: "Resets the sequence" },
  { kind: "conversation", label: "Spoke", hint: "A call or coffee chat happened" },
  { kind: "referral_asked", label: "Asked for a referral", hint: "" },
  { kind: "referral_confirmed", label: "They referred me", hint: "Counts in the funnel split" },
  { kind: "thank_you", label: "Sent a thank-you", hint: "" },
  { kind: "note", label: "Note", hint: "Does not affect the clock" },
];

export function NetworkPage() {
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [overview, setOverview] = useState<NetworkOverview | null>(null);
  const [referrals, setReferrals] = useState<ReferralReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [drafting, setDrafting] = useState<{ contact: Contact; kind: string } | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, o, r] = await Promise.all([
        api.contacts(),
        api.networkOverview(7),
        api.referralSplit(),
      ]);
      setContacts(c);
      setOverview(o);
      setReferrals(r);
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const log = async (id: string, kind: InteractionKind, on: string, summary: string) => {
    setBusyId(id);
    try {
      await api.logInteraction(id, { kind, occurred_at: atMidday(on), summary });
      await load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (id: string) => {
    setBusyId(id);
    try {
      await api.deleteContact(id);
      await load();
    } finally {
      setBusyId(null);
    }
  };

  if (error && !contacts)
    return (
      <CenteredNote>
        <p className="text-bad">Could not reach the API.</p>
        <p className="text-2xs text-navy-400 mt-1">Is the backend running on :8077?</p>
      </CenteredNote>
    );
  if (!contacts || !overview) return <CenteredNote>Loading your network…</CenteredNote>;

  const gaps = overview.coverage.filter((c) => c.is_target && c.contact_count === 0);

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-lg font-700 text-navy-900">Your network</h1>
          <p className="text-sm text-navy-500 mt-1 max-w-2xl leading-relaxed">
            {overview.note}
          </p>
        </div>
        <button onClick={() => setAdding((v) => !v)} className="btn-toggle text-xs shrink-0">
          {adding ? "Close" : "Add contacts"}
        </button>
      </div>

      {error && <div className="card p-2.5 border-bad/30 bg-bad/5 text-xs text-bad">{error}</div>}

      {adding && (
        <ContactPaste
          school={overview.school}
          onSaved={async (n) => {
            setAdding(false);
            await load();
            setError(null);
            if (n === 0) setError("Nothing was saved.");
          }}
        />
      )}

      {/* Due first. A queue you can finish is the only kind anyone works. */}
      <section className="card p-4">
        <h2 className="rule-label mb-2">Due now</h2>
        {overview.queue.length === 0 ? (
          <p className="text-xs text-navy-400">
            Nothing due in the next week. Everything you've started is either waiting on them or
            finished.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {overview.queue.map((q) => {
              const contact = contacts.find((c) => c.id === q.contact_id);
              return (
                <li key={q.contact_id} className="flex items-baseline gap-2 text-xs flex-wrap">
                  <span className="font-600 text-navy-900">{q.name}</span>
                  {q.company_name && <span className="text-navy-400">{q.company_name}</span>}
                  <span className="text-navy-600">{q.step.action}</span>
                  <span
                    className={`text-2xs tabular-nums ${
                      q.step.status.includes("late") ? "text-beacon-700 font-600" : "text-navy-400"
                    }`}
                  >
                    {q.step.status}
                  </span>
                  {contact && (
                    <button
                      onClick={() => setDrafting({ contact, kind: q.step.draft_kind })}
                      className="btn-ghost text-2xs px-1.5 py-0.5 ml-auto"
                    >
                      Draft it
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Where the network is thin. The actionable half of "who do I know". */}
      {gaps.length > 0 && (
        <section className="card p-4">
          <h2 className="rule-label mb-2">Target companies where you know nobody</h2>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5">
            {gaps.map((c) => (
              <span key={c.company_name} className="term border-beacon-500 text-navy-700">
                {c.company_name}
                {c.open_postings > 0 && (
                  <span className="term-count">{c.open_postings} open</span>
                )}
              </span>
            ))}
          </div>
          <p className="text-2xs text-navy-400 mt-2 leading-relaxed max-w-2xl">
            LinkedIn's Alumni tool, filtered by "where they work", is the fastest way to close
            these. Paste the results into Add contacts — Lighthouse never touches your account.
          </p>
        </section>
      )}

      {referrals && referrals.referred.applied + referrals.cold.applied > 0 && (
        <section className="card p-4">
          <h2 className="rule-label mb-2">Referred vs cold</h2>
          <p className="text-xs text-navy-600">{referrals.note}</p>
        </section>
      )}

      {contacts.length === 0 ? (
        <EmptyNetwork />
      ) : (
        <div className="space-y-2">
          {contacts.map((c) => (
            <ContactRow
              key={c.id}
              contact={c}
              busy={busyId === c.id}
              onLog={log}
              onDelete={remove}
              onDraft={(kind) => setDrafting({ contact: c, kind })}
            />
          ))}
        </div>
      )}

      {drafting && (
        <DraftPanel
          contact={drafting.contact}
          kind={drafting.kind}
          onClose={() => setDrafting(null)}
          onLogged={async (kind) => {
            await log(drafting.contact.id, kind, today(), "Sent from a Lighthouse draft");
            setDrafting(null);
          }}
        />
      )}
    </div>
  );
}

function ContactRow({
  contact,
  busy,
  onLog,
  onDelete,
  onDraft,
}: {
  contact: Contact;
  busy: boolean;
  onLog: (id: string, kind: InteractionKind, on: string, summary: string) => void;
  onDelete: (id: string) => void;
  onDraft: (kind: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [on, setOn] = useState(today());
  const [summary, setSummary] = useState("");

  return (
    <div className="card p-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <button onClick={() => setOpen((v) => !v)} className="text-left min-w-0 flex-1">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-sm font-600 text-navy-900">{contact.name}</span>
            {contact.is_alumni && (
              <span className="text-2xs text-good" title="Same school as you">
                alumni
              </span>
            )}
            <span className="text-2xs text-navy-400">
              {[contact.role_title, contact.company_name].filter(Boolean).join(" · ")}
            </span>
          </div>
          <div className="flex items-baseline gap-2 mt-0.5 flex-wrap">
            <span className="text-2xs text-navy-500">{contact.stage_label}</span>
            {contact.silence_note && (
              <span
                className={`text-2xs ${
                  (contact.days_since_outbound ?? 0) >= 14
                    ? "text-beacon-700"
                    : "text-navy-400"
                }`}
              >
                {contact.silence_note}
              </span>
            )}
            {contact.referral_confirmed && (
              <span className="text-2xs text-good">referred you</span>
            )}
          </div>
        </button>

        <div className="flex items-center gap-1.5 shrink-0">
          {contact.next_step && (
            <>
              <span
                className={`text-2xs tabular-nums ${
                  contact.next_step.status.includes("late")
                    ? "text-beacon-700 font-600"
                    : "text-navy-400"
                }`}
                title={contact.next_step.reason}
              >
                {contact.next_step.action} · {contact.next_step.status}
              </span>
              <button
                onClick={() => onDraft(contact.next_step!.draft_kind)}
                className="btn-toggle text-2xs px-2 py-0.5"
              >
                Draft
              </button>
            </>
          )}
          {/* The sequence is over. Say so, and stop offering to continue it. */}
          {!contact.next_step && contact.cadence_note && (
            <span className="text-2xs text-navy-400 max-w-[22rem] text-right">
              {contact.cadence_note}
            </span>
          )}
        </div>
      </div>

      {open && (
        <div className="mt-3 pt-2.5 border-t border-navy-100 space-y-2.5">
          {contact.timeline.length > 0 && (
            <ol className="space-y-1">
              {contact.timeline.map((e) => (
                <li key={e.id} className="text-2xs text-navy-500 flex gap-2">
                  <span className="tabular-nums text-navy-400 shrink-0">
                    {e.occurred_at.slice(0, 10)}
                  </span>
                  <span className={e.direction === "inbound" ? "text-good" : "text-navy-700"}>
                    {e.label}
                  </span>
                  {e.summary && <span className="text-navy-400 italic">{e.summary}</span>}
                </li>
              ))}
            </ol>
          )}

          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 flex-wrap">
              <input
                type="date"
                value={on}
                max={today()}
                onChange={(e) => setOn(e.target.value || today())}
                title="When this actually happened"
                className="text-2xs bg-white border border-navy-200 rounded px-1.5 py-0.5
                           text-navy-700 hover:border-navy-300 focus:border-beacon-500 outline-none"
              />
              <input
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder="What was actually discussed — a follow-up three weeks later reads this"
                className="text-2xs bg-white border border-navy-200 rounded px-2 py-0.5 flex-1
                           min-w-[14rem] text-navy-700 placeholder:text-navy-300
                           hover:border-navy-300 focus:border-beacon-500 outline-none"
              />
            </div>
            <div className="flex flex-wrap gap-1">
              {LOGGABLE.map((l) => (
                <button
                  key={l.kind}
                  title={l.hint}
                  disabled={busy}
                  onClick={() => {
                    onLog(contact.id, l.kind, on, summary);
                    setSummary("");
                  }}
                  className="text-2xs px-1.5 py-0.5 rounded text-navy-600 hover:text-beacon-700
                             hover:bg-beacon-glow transition-colors disabled:opacity-40"
                >
                  {l.label}
                </button>
              ))}
              <button
                onClick={() => onDelete(contact.id)}
                disabled={busy}
                className="text-2xs px-1.5 py-0.5 rounded text-navy-400 hover:text-bad
                           hover:bg-bad/5 transition-colors ml-auto"
              >
                Remove
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyNetwork() {
  return (
    <div className="rounded-xl border border-dashed border-navy-200 p-10 text-center">
      <p className="text-sm text-navy-700">No contacts yet.</p>
      <p className="text-2xs text-navy-400 mt-1 max-w-lg mx-auto leading-relaxed">
        Open your school's page on LinkedIn, use its Alumni tool, filter by where they work, and
        paste the results into Add contacts. That tool exists for exactly this — Lighthouse reads
        what you paste and never touches your account.
      </p>
    </div>
  );
}

function CenteredNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center text-sm text-navy-600 py-24">
      {children}
    </div>
  );
}
