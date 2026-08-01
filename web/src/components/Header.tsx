import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CycleCount, SourceHealth } from "../api/types";

// The masthead: the mark, the live cycle counts (which answer "is there
// anything worth applying to right now?"), and a quiet source-health indicator.

function Beacon() {
  return (
    <div className="relative flex items-center justify-center h-7 w-7">
      <div className="absolute h-7 w-7 rounded-full bg-beacon-glow animate-sweep" />
      <div className="h-2.5 w-2.5 rounded-full bg-beacon-500 shadow-[0_0_12px_rgba(240,165,46,0.8)]" />
    </div>
  );
}

export type View = "discover" | "corpus" | "resume";

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
    <header className="border-b border-ink-800 bg-ink-950/80 backdrop-blur sticky top-0 z-30">
      <div className="px-6 py-3 flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <Beacon />
          <div>
            <div className="text-sm font-700 text-mist-100 tracking-tight leading-none">
              Lighthouse
            </div>
            <div className="text-2xs text-mist-400 leading-none mt-0.5">internship command center</div>
          </div>
        </div>

        <nav className="flex items-center gap-1">
          <NavItem active={view === "discover"} onClick={() => onView("discover")}>
            Discover
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
              className="chip border-ink-700 shrink-0"
              title={`${c.count} active postings for ${c.term_label}`}
            >
              <span className="text-mist-200">{c.term_label}</span>
              <span className="text-beacon-400 tabular-nums font-600">{c.count}</span>
            </div>
          ))}
        </div>

        <div
          className="flex items-center gap-1.5 text-2xs text-mist-400 shrink-0"
          title={`${okSources} sources healthy, ${quarantined} with issues`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${quarantined ? "bg-warn" : "bg-good"}`}
          />
          {okSources} sources
          {quarantined > 0 && <span className="text-warn">· {quarantined} need attention</span>}
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
        active ? "bg-ink-800 text-mist-100" : "text-mist-400 hover:text-mist-200 hover:bg-ink-850"
      }`}
    >
      {children}
    </button>
  );
}
