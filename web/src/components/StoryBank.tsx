import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Fact, Story, StoryBank as Bank, StoryInput } from "../api/types";

// The story bank: your behavioral answers, tied to the same facts your résumé
// reads from.
//
// What makes this more than a notes app is the coverage strip. Most behavioral
// questions are a handful of competencies asked a hundred ways, so "no story
// tagged conflict" is a finite hole you can close this afternoon — which beats
// the vague sense of being underprepared that it replaces.
//
// Nothing is inferred from the prose. A story counts for a competency because
// you tagged it, not because it "sounds like" one: guessing would invent a
// coverage you never claimed, and you'd find out in the room.

export function StoryBank({ facts }: { facts: Fact[] }) {
  const [bank, setBank] = useState<Bank | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setBank(await api.stories());
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async (input: StoryInput, id?: string) => {
    setBusy(true);
    try {
      if (id) await api.updateStory(id, input);
      else await api.createStory(input);
      setEditing(null);
      setAdding(false);
      await load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    try {
      await api.deleteStory(id);
      await load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  if (!bank) return null;

  return (
    <section className="card p-4 space-y-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start justify-between gap-4 text-left"
      >
        <div>
          <h2 className="text-sm font-700 text-navy-900">Your stories</h2>
          <p className="text-2xs text-navy-500 mt-0.5 max-w-2xl leading-relaxed">{bank.note}</p>
        </div>
        <span className="text-2xs text-navy-400 shrink-0 mt-0.5">{open ? "−" : "+"}</span>
      </button>

      <CompetencyStrip bank={bank} />

      {open && (
        <div className="space-y-3 pt-1">
          {error && (
            <div className="card p-2.5 border-bad/30 bg-bad/5 text-xs text-bad">{error}</div>
          )}

          {bank.reliance.length > 0 && (
            <div className="card p-3 border-warn/30 bg-warn/5">
              {bank.reliance.map((r) => (
                <p key={r.fact_id} className="text-2xs text-navy-700">
                  <span className="font-600">
                    {r.story_count} of {bank.story_count} stories
                  </span>{" "}
                  draw on <span className="font-600">{r.fact_title}</span>. An interviewer hearing
                  the same project four times notices.
                </p>
              ))}
            </div>
          )}

          <div className="space-y-2">
            {bank.stories.map((story) =>
              editing === story.id ? (
                <div key={story.id} className="card p-3">
                  <StoryEditor
                    story={story}
                    facts={facts}
                    competencies={bank.competencies}
                    saving={busy}
                    onSave={(input) => save(input, story.id)}
                    onCancel={() => setEditing(null)}
                  />
                </div>
              ) : (
                <StoryRow
                  key={story.id}
                  story={story}
                  facts={facts}
                  onEdit={() => setEditing(story.id)}
                  onDelete={() => remove(story.id)}
                  busy={busy}
                />
              ),
            )}
          </div>

          {adding ? (
            <div className="card p-3">
              <StoryEditor
                facts={facts}
                competencies={bank.competencies}
                saving={busy}
                onSave={(input) => save(input)}
                onCancel={() => setAdding(false)}
              />
            </div>
          ) : (
            <button onClick={() => setAdding(true)} className="btn-toggle text-xs">
              + Add a story
            </button>
          )}
        </div>
      )}
    </section>
  );
}

/** The coverage strip. Covered competencies are quiet; the gaps carry the
 *  beacon, because they are the only actionable thing on the row. */
function CompetencyStrip({ bank }: { bank: Bank }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1.5">
      {bank.competencies.map((c) => (
        <span
          key={c.slug}
          title={
            c.story_count > 0
              ? `${c.prompt} — ${c.story_titles.join(", ")}`
              : `${c.prompt} — nothing covers this yet`
          }
          className={`term ${
            c.story_count > 0 ? "border-good text-navy-600" : "border-beacon-500 text-navy-700"
          }`}
        >
          {c.slug}
          {c.story_count > 1 && (
            <span className="text-navy-400 tabular-nums"> ×{c.story_count}</span>
          )}
        </span>
      ))}
    </div>
  );
}

function StoryRow({
  story,
  facts,
  onEdit,
  onDelete,
  busy,
}: {
  story: Story;
  facts: Fact[];
  onEdit: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const sources = facts.filter((f) => story.source_fact_ids.includes(f.id));

  return (
    <div className="border-l-2 border-navy-200 pl-3 py-1">
      <div className="flex items-start justify-between gap-3">
        <button onClick={() => setOpen((v) => !v)} className="text-left min-w-0 flex-1">
          <span className="text-xs font-600 text-navy-900">{story.title}</span>
          {!story.is_grounded && (
            <span className="ml-2 text-2xs text-warn" title="Not tied to any corpus fact">
              unverified
            </span>
          )}
          <div className="text-2xs text-navy-400 mt-0.5">
            {story.competency_tags.length > 0
              ? story.competency_tags.join(" · ")
              : "no competencies tagged"}
          </div>
        </button>
        <div className="flex gap-1 shrink-0">
          <button onClick={onEdit} disabled={busy} className="btn-ghost text-2xs px-1.5 py-0.5">
            Edit
          </button>
          <button
            onClick={onDelete}
            disabled={busy}
            className="btn-ghost text-2xs px-1.5 py-0.5 hover:text-bad"
          >
            Delete
          </button>
        </div>
      </div>

      {open && (
        <div className="mt-2 space-y-1.5">
          {(
            [
              ["Situation", story.situation],
              ["Task", story.task],
              ["Action", story.action],
              ["Result", story.result],
            ] as const
          ).map(([label, value]) =>
            value ? (
              <p key={label} className="text-2xs text-navy-600 leading-relaxed">
                <span className="text-navy-400 uppercase tracking-wide">{label}</span> {value}
              </p>
            ) : null,
          )}
          {/* The zero-fabrication trace, rendered. If this line is empty the
              story is asserting something the corpus cannot back. */}
          <p className="text-2xs text-navy-400 pt-1">
            {sources.length > 0
              ? `Built from: ${sources.map((f) => f.title).join(", ")}`
              : "Not built from anything in your corpus yet."}
          </p>
        </div>
      )}
    </div>
  );
}

function StoryEditor({
  story,
  facts,
  competencies,
  saving,
  onSave,
  onCancel,
}: {
  story?: Story;
  facts: Fact[];
  competencies: { slug: string; prompt: string }[];
  saving: boolean;
  onSave: (input: StoryInput) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<StoryInput>({
    title: story?.title ?? "",
    situation: story?.situation ?? "",
    task: story?.task ?? "",
    action: story?.action ?? "",
    result: story?.result ?? "",
    source_fact_ids: story?.source_fact_ids ?? [],
    competency_tags: story?.competency_tags ?? [],
  });

  const set = <K extends keyof StoryInput>(key: K, value: StoryInput[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const toggle = (key: "source_fact_ids" | "competency_tags", value: string) => {
    const current = draft[key] ?? [];
    set(key, current.includes(value) ? current.filter((v) => v !== value) : [...current, value]);
  };

  const field = (label: string, key: "situation" | "task" | "action" | "result", hint: string) => (
    <label className="block">
      <span className="text-2xs text-navy-400 uppercase tracking-wide">{label}</span>
      <textarea
        value={draft[key] ?? ""}
        onChange={(e) => set(key, e.target.value)}
        rows={2}
        placeholder={hint}
        className="field text-xs mt-0.5 resize-y"
      />
    </label>
  );

  return (
    <div className="space-y-2.5">
      <input
        autoFocus
        value={draft.title}
        onChange={(e) => set("title", e.target.value)}
        placeholder="What you'd call this, e.g. “Rewrote the ingest pipeline”"
        className="field text-xs font-600"
      />

      {field("Situation", "situation", "What was going on")}
      {field("Task", "task", "What you were responsible for")}
      {field("Action", "action", "What you actually did")}
      {field(
        "Result",
        "result",
        "How it turned out — a number if you have one. This is the part most people leave vague.",
      )}

      <div>
        <span className="text-2xs text-navy-400 uppercase tracking-wide">Competencies</span>
        <div className="flex flex-wrap gap-1 mt-1">
          {competencies.map((c) => (
            <button
              key={c.slug}
              title={c.prompt}
              onClick={() => toggle("competency_tags", c.slug)}
              className={
                draft.competency_tags?.includes(c.slug) ? "btn-filter-on" : "btn-filter"
              }
            >
              {c.slug}
            </button>
          ))}
        </div>
      </div>

      <div>
        <span className="text-2xs text-navy-400 uppercase tracking-wide">Built from</span>
        <p className="text-2xs text-navy-400 mb-1">
          Which of your facts this is about. A story with none is stored, but flagged — and never
          used to ground anything.
        </p>
        <div className="flex flex-wrap gap-1">
          {facts.map((f) => (
            <button
              key={f.id}
              onClick={() => toggle("source_fact_ids", f.id)}
              className={draft.source_fact_ids?.includes(f.id) ? "btn-filter-on" : "btn-filter"}
            >
              {f.title}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => onSave(draft)}
          disabled={saving || !draft.title.trim()}
          className="btn-primary text-xs"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button onClick={onCancel} className="btn-toggle text-xs">
          Cancel
        </button>
      </div>
    </div>
  );
}
