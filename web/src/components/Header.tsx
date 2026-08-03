import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CycleCount, SourceHealth } from "../api/types";

// The masthead: the mark, the live cycle counts (which answer "is there
// anything worth applying to right now?"), and a quiet source-health indicator.
//
// It is the one navy band on an otherwise white page, which is the whole
// identity in one element: a lit tower against the dark. Everything below it is
// paper, so the eye starts here and then goes to work.

function Beacon() {
  return (
    <div className="relative flex items-center justify-center h-7 w-7">
      <div className="absolute h-7 w-7 rounded-full bg-beacon-500/25 blur-[6px] animate-sweep" />
      <div className="h-2.5 w-2.5 rounded-full bg-beacon-400 shadow-[0_0_14px_3px_rgba(245,162,74,0.75)]" />
    </div>
  );
}

export type View = "discover" | "track" | "corpus" | "resume";

export function Header({ view, onView }: { view: View; onView: (v: View) => void }) {
  const [cycles, setCycles] = useState<CycleCount[]>([]);
  const [health, setHealth] = useState<SourceHealth[]>([]);

  useEffect(() => {
    api.cycles().then(setCycles).catch(() => {});
    api.sourceHealth().then(setHealth).catch(() => {});
  }, []);

  const quarantined = health.filter((h) => h.is_quarantined || h.last_error).length;
  const okSources = health.filter((h) => h.last_success_at && !h.is_quarantined).length;

  return (
    // The hairline at the bottom edge is the lamp catching the top of the page.
    <header className="bg-navy-900 sticky top-0 z-30 shadow-[inset_0_-1px_0_rgba(239,132,32,0.45)]">
      <div className="px-6 py-3 flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <Beacon />
          <div>
            <div className="text-sm font-700 text-white tracking-tight leading-none">Lighthouse</div>
            <div className="text-2xs text-navy-300 leading-none mt-0.5">
              internship command center
            </div>
          </div>
        </div>

        <nav className="flex items-center gap-1">
          <NavItem active={view === "discover"} onClick={() => onView("discover")}>
            Discover
          </NavItem>
          <NavItem active={view === "track"} onClick={() => onView("track")}>
            Applications
          </NavItem>
          <NavItem active={view === "corpus"} onClick={() => onView("corpus")}>
            My corpus
          </NavItem>
          <NavItem active={view === "resume"} onClick={() => onView("resume")}>
            Résumé check
          </NavItem>
        </nav>

        <div className="flex-1 flex items-center gap-1.5 overflow-x-auto no-scrollbar">
          {view === "discover" &&
            cycles.map((c) => (
            <div
              key={c.term_label}
              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-2xs
                         font-medium border border-white/10 bg-white/[0.06] shrink-0"
              title={`${c.count} active postings for ${c.term_label}`}
            >
              <span className="text-navy-200">{c.term_label}</span>
              <span className="text-beacon-400 tabular-nums font-600">{c.count}</span>
            </div>
          ))}
        </div>

        <div
          className="flex items-center gap-1.5 text-2xs text-navy-300 shrink-0"
          title={`${okSources} sources healthy, ${quarantined} with issues`}
        >
          {/* Healthy is deliberately quiet — a white dot, not a green light.
              Only trouble earns the beacon colour. */}
          <span
            className={`h-1.5 w-1.5 rounded-full ${quarantined ? "bg-beacon-400" : "bg-white/50"}`}
          />
          {okSources} sources
          {quarantined > 0 && <span className="text-beacon-400">· {quarantined} need attention</span>}
        </div>
      </div>
    </header>
  );
}

function NavItem({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-sm font-500 transition-colors ${
        active ? "bg-white/[0.12] text-white" : "text-navy-300 hover:text-white hover:bg-white/[0.06]"
      }`}
    >
      {children}
    </button>
  );
}
