import { useState } from "react";
import type { Fact, FactContribution, FactInput, FactType } from "../api/types";
import { FACT_TYPES, FactEditor } from "./FactEditor";

// The corpus, grouped by kind, with each fact carrying what it's actually worth
// in the postings currently ingested. That last part is the whole reason this
// isn't just a list with edit buttons: "does adding this project help me?" is
// answerable from real counts, and the answer is often "you already had it
// covered" — which is exactly what unique reach is there to say.

const TYPE_ORDER: FactType[] = ["experience", "project", "education", "achievement", "skill"];

export function FactList({
  facts,
  contributions,
  sampleSize,
  onUpdate,
  onDelete,
  busyId,
}: {
  facts: Fact[];
  contributions: Map<string, FactContribution>;
  sampleSize: number;
  onUpdate: (id: string, fact: FactInput) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  busyId: string | null;
}) {
  const grouped = TYPE_ORDER.map((type) => ({
    type,
    label: FACT_TYPES.find((t) => t.value === type)?.label ?? type,
    items: facts.filter((f) => f.fact_type === type),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="space-y-6">
      {grouped.map((group) => (
        <section key={group.type}>
          <h3 className="text-2xs font-600 uppercase tracking-wide text-navy-600 mb-2">
            {group.label}
            <span className="text-navy-400 font-400 normal-case tracking-normal">
              {" "}
              · {group.items.length}
            </span>
          </h3>
          {/* A skill is one word with one term behind it. Giving each its own
              card buries the entries that carry real detail, so they get a
              dense grid instead — same numbers, proportionate space. */}
          <div className={group.type === "skill" ? "grid sm:grid-cols-2 gap-1.5" : "space-y-2"}>
            {group.items.map((fact) => (
              <FactRow
                key={fact.id}
                fact={fact}
                contribution={contributions.get(fact.id)}
                sampleSize={sampleSize}
                onUpdate={onUpdate}
                onDelete={onDelete}
                busy={busyId === fact.id}
                compact={group.type === "skill" && !fact.body}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function FactRow({
  fact,
  contribution,
  sampleSize,
  onUpdate,
  onDelete,
  busy,
  compact = false,
}: {
  fact: Fact;
  contribution?: FactContribution;
  sampleSize: number;
  onUpdate: (id: string, fact: FactInput) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  busy: boolean;
  compact?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (editing) {
    return (
      <div className="card p-3">
        <FactEditor
          initial={{ fact_type: fact.fact_type, title: fact.title, body: fact.body }}
          saving={busy}
          autoFocus
          onCancel={() => setEditing(false)}
          onSave={async (next) => {
            await onUpdate(fact.id, next);
            setEditing(false);
          }}
        />
      </div>
    );
  }

  if (compact) {
    const reach = contribution?.reach ?? 0;
    const redundant = contribution != null && reach > 0 && contribution.unique_reach === 0;
    return (
      <div className="card px-2.5 py-2 group hover:border-navy-300 transition-colors flex items-center gap-2">
        <span className="text-xs text-navy-900 font-500 truncate">{fact.title}</span>
        <span
          className="text-2xs text-navy-400 tabular-nums shrink-0"
          title={`Mentioned in ${reach} of ${sampleSize} sampled postings`}
        >
          {reach}
        </span>
        {redundant && (
          <span
            className="text-2xs text-navy-300 shrink-0"
            title="Every posting this reaches is already reached by another fact — usually because a project or job below already describes it."
          >
            covered elsewhere
          </span>
        )}
        <span className="flex-1" />
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button onClick={() => setEditing(true)} className="btn-ghost text-2xs px-1.5 py-0.5">
            Edit
          </button>
          <button
            onClick={() => (confirmDelete ? onDelete(fact.id) : setConfirmDelete(true))}
            disabled={busy}
            className={`btn text-2xs px-1.5 py-0.5 ${
              confirmDelete ? "text-bad hover:bg-bad/10" : "text-navy-600 hover:text-bad"
            }`}
          >
            {busy ? "…" : confirmDelete ? "Sure?" : "Delete"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="card p-3 group hover:border-navy-300 transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-navy-900 font-500 leading-snug">{fact.title}</p>
          {fact.body && (
            <p className="text-xs text-navy-500 mt-1 leading-relaxed whitespace-pre-line line-clamp-3">
              {fact.body}
            </p>
          )}
          {contribution && <Contribution contribution={contribution} sampleSize={sampleSize} />}
        </div>

        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button onClick={() => setEditing(true)} className="btn-ghost text-2xs px-2 py-1">
            Edit
          </button>
          {confirmDelete ? (
            <>
              <button
                onClick={() => onDelete(fact.id)}
                disabled={busy}
                className="btn text-2xs px-2 py-1 text-bad hover:bg-bad/10"
              >
                {busy ? "…" : "Really delete"}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="btn-ghost text-2xs px-2 py-1"
              >
                No
              </button>
            </>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="btn-ghost text-2xs px-2 py-1 hover:text-bad"
            >
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * What this fact buys, in observed counts. Never a score: "mentioned in 68 of
 * 425 postings" is checkable, "82% relevant" would be invented.
 */
function Contribution({
  contribution,
  sampleSize,
}: {
  contribution: FactContribution;
  sampleSize: number;
}) {
  const { reach, unique_reach, terms, unmatched_term_count } = contribution;

  if (terms.length === 0) {
    return (
      <p className="text-2xs text-navy-400 mt-2">
        No term here matches anything in the {sampleSize} postings sampled.
        {unmatched_term_count > 0 && " That may just mean your field isn't well covered yet."}
      </p>
    );
  }

  return (
    <div className="mt-2 space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs">
        <span className="text-navy-600">
          <span className="font-mono font-600 text-beacon-600 tabular-nums">{reach}</span>
          <span className="text-navy-400"> of {sampleSize} postings mention its terms</span>
        </span>
        {unique_reach > 0 ? (
          <span
            className="text-navy-600"
            title="Postings this fact reaches that none of your other facts do. This is what makes it worth its space on the résumé."
          >
            <span className="font-mono font-600 text-good tabular-nums">{unique_reach}</span>
            <span className="text-navy-400"> only this fact reaches</span>
          </span>
        ) : (
          <span
            className="text-navy-400"
            title="Every posting this reaches is already reached by another fact. Not wrong to keep — but it isn't adding coverage."
          >
            adds no coverage your other facts don't
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {terms.slice(0, 8).map((t) => (
          <span
            key={t.term}
            className="term border-navy-200"
            title={`"${t.term}" appears in ${t.posting_count} sampled postings${
              t.core_count > 0 ? `, and is central to ${t.core_count} of them` : ""
            }`}
          >
            {t.term}
            <span className="term-count">{t.posting_count}</span>
          </span>
        ))}
        {terms.length > 8 && (
          <span className="text-2xs text-navy-400 self-center">+{terms.length - 8} more</span>
        )}
      </div>
    </div>
  );
}
