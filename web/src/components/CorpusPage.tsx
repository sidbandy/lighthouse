import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  Corpus,
  Coverage,
  FactContribution,
  FactInput,
  Onboarding,
  OnboardingStep,
  RoleFamily,
} from "../api/types";
import { CoveragePanel } from "./CoveragePanel";
import { FactEditor } from "./FactEditor";
import { FactList } from "./FactList";
import { ResumeImport } from "./ResumeImport";
import { SetupPanel } from "./SetupPanel";

// The corpus page: the operator's own facts, and the setup that makes the rest
// of Lighthouse personal. Match scoring, the résumé tailor and (later) story
// grounding all read from what's edited here — so this page is the difference
// between the tool scoring postings against a stranger and scoring them against
// you.

const STEP_COPY: Record<OnboardingStep, { title: string; detail: string }> = {
  upload_resume: {
    title: "Start with your résumé",
    detail:
      "Nothing personal exists yet, so every match score is currently zero. Import a résumé, or add a project by hand — either works.",
  },
  add_projects: {
    title: "Add a few more real things",
    detail:
      "Matching works from three facts, but it gets sharper fast. Projects with real detail are worth the most — they carry the vocabulary postings actually use.",
  },
  pick_targets: {
    title: "Pick some target companies",
    detail:
      "Targets seed the three-lane view and tell Lighthouse which boards to poll directly for full descriptions.",
  },
  set_constraints: {
    title: "Set your constraints",
    detail: "Location, work authorization and study time seed your filters.",
  },
  complete: { title: "Setup complete", detail: "" },
};

export function CorpusPage() {
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [onboarding, setOnboarding] = useState<Onboarding | null>(null);
  const [roleFilter, setRoleFilter] = useState<RoleFamily | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [showSetup, setShowSetup] = useState(false);

  const loadCorpus = useCallback(async () => {
    const [c, o] = await Promise.all([api.corpus(), api.onboarding()]);
    setCorpus(c);
    setOnboarding(o);
  }, []);

  const loadCoverage = useCallback(async () => {
    setCoverage(await api.coverage(roleFilter ? [roleFilter] : undefined));
  }, [roleFilter]);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadCorpus(), loadCoverage()])
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Coverage is the expensive call, so it reloads on its own when the market
  // filter changes rather than dragging the whole page with it.
  useEffect(() => {
    if (!loading) loadCoverage().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roleFilter]);

  const announce = (message: string) => {
    setFlash(message);
    setTimeout(() => setFlash(null), 2500);
  };

  const refresh = async () => {
    await Promise.all([loadCorpus(), loadCoverage()]);
  };

  const create = async (fact: FactInput) => {
    setBusyId("new");
    try {
      await api.createFact(fact);
      setAdding(false);
      await refresh();
      announce("Added. Match scores now include it.");
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusyId(null);
    }
  };

  const update = async (id: string, fact: FactInput) => {
    setBusyId(id);
    try {
      await api.updateFact(id, fact);
      await refresh();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (id: string) => {
    setBusyId(id);
    try {
      await api.deleteFact(id);
      await refresh();
      announce("Deleted.");
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusyId(null);
    }
  };

  if (loading) {
    return <CenteredNote>Loading your corpus…</CenteredNote>;
  }

  if (error && !corpus) {
    return (
      <CenteredNote>
        <p className="text-bad">Could not reach the API.</p>
        <p className="text-2xs text-mist-400 mt-1">Is the backend running on :8077?</p>
      </CenteredNote>
    );
  }

  if (!corpus || !onboarding || !coverage) return null;

  const contributions = new Map<string, FactContribution>(
    coverage.contributions.map((c) => [c.fact_id, c]),
  );
  const step = STEP_COPY[onboarding.next_step];
  const empty = corpus.summary.fact_count === 0;

  return (
    <div className="max-w-5xl mx-auto px-6 py-6 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-700 text-mist-100">Your corpus</h1>
          <p className="text-sm text-mist-400 mt-1 max-w-2xl">
            Every real thing you've done, in one place. Match scoring, the résumé tailor and your
            interview stories all read from here — which is what stops your résumé and your answers
            telling two different versions of the same history.
          </p>
        </div>
        {!empty && (
          <button onClick={() => setShowSetup((v) => !v)} className="btn-toggle text-xs shrink-0">
            {showSetup ? "Hide setup" : "Targets & constraints"}
          </button>
        )}
      </div>

      {!onboarding.is_complete && (
        <div className="card p-4 border-beacon-500/30 bg-beacon-glow">
          <div className="flex items-start gap-3">
            <span className="text-beacon-400 text-sm mt-0.5">→</span>
            <div className="flex-1">
              <p className="text-sm font-600 text-mist-100">{step.title}</p>
              <p className="text-xs text-mist-300 mt-1 leading-relaxed">{step.detail}</p>
              {(onboarding.next_step === "pick_targets" ||
                onboarding.next_step === "set_constraints") &&
                !showSetup && (
                  <button
                    onClick={() => setShowSetup(true)}
                    className="btn-primary text-xs mt-2.5"
                  >
                    Open setup
                  </button>
                )}
            </div>
          </div>
        </div>
      )}

      {flash && (
        <div className="card p-2.5 border-good/30 bg-good/5 text-xs text-good animate-fade-in">
          {flash}
        </div>
      )}
      {error && corpus && (
        <div className="card p-2.5 border-bad/30 bg-bad/5 text-xs text-bad">{error}</div>
      )}

      {showSetup && <SetupPanel onboarding={onboarding} onChange={setOnboarding} />}

      {!empty && (
        <CoveragePanel
          coverage={coverage}
          roleFilter={roleFilter}
          onRoleFilter={setRoleFilter}
        />
      )}

      <ResumeImport
        onImported={async (count) => {
          await refresh();
          announce(`Saved ${count} fact${count !== 1 ? "s" : ""} from your résumé.`);
        }}
      />

      <div className="flex items-center justify-between">
        <p className="text-2xs text-mist-400">{corpus.summary.readiness_note}</p>
        {!adding && (
          <button onClick={() => setAdding(true)} className="btn-toggle text-xs">
            + Add a fact
          </button>
        )}
      </div>

      {adding && (
        <div className="card p-3 animate-fade-in">
          <FactEditor
            autoFocus
            saving={busyId === "new"}
            onSave={create}
            onCancel={() => setAdding(false)}
          />
        </div>
      )}

      {empty ? (
        <CenteredNote>
          <p>Nothing here yet.</p>
          <p className="text-2xs text-mist-400 mt-1">
            Import a résumé above, or add your first project by hand.
          </p>
        </CenteredNote>
      ) : (
        <FactList
          facts={corpus.facts}
          contributions={contributions}
          sampleSize={coverage.sample_size}
          onUpdate={update}
          onDelete={remove}
          busyId={busyId}
        />
      )}
    </div>
  );
}

function CenteredNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center text-sm text-mist-300 py-24">
      {children}
    </div>
  );
}
