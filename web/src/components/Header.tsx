import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { CycleCount, SourceHealth } from "../api/types";
import { RefreshButton } from "./RefreshButton";
import { SourcePanel } from "./SourcePanel";

// The masthead: the mark, the live cycle counts (which answer "is there
// anything worth applying to right now?"), and a quiet source-health indicator.
//
// It is the one navy band on an otherwise white page, which is the whole
// identity in one element: a lit tower against the dark. Everything below it is
// paper, so the eye starts here and then goes to work.
//
// Seven nav links, the cycle chips and two controls do not fit a phone -- laid
// out in one row they need about 950px, which is why the whole page used to
// scroll sideways at 390px. Below `lg` the links move into a menu instead, and
// the cycle counts and refresh go with them, because on a phone the question
// "is there anything worth applying to right now?" is the reason you opened the
// app at all.

function Beacon() {
  return (
    <div className="relative flex items-center justify-center h-7 w-7">
      <div className="absolute h-7 w-7 rounded-full bg-beacon-500/25 blur-[6px] animate-sweep" />
      <div className="h-2.5 w-2.5 rounded-full bg-beacon-400 shadow-[0_0_14px_3px_rgba(245,162,74,0.75)]" />
    </div>
  );
}

const NAV: { to: string; label: string }[] = [
  { to: "/discover", label: "Discover" },
  { to: "/applications", label: "Applications" },
  { to: "/network", label: "Network" },
  { to: "/study", label: "Study" },
  { to: "/practice", label: "Practice" },
  { to: "/corpus", label: "My corpus" },
  { to: "/resume", label: "Résumé check" },
];

export function Header({ onRefreshed }: { onRefreshed?: () => void }) {
  const [cycles, setCycles] = useState<CycleCount[]>([]);
  const [health, setHealth] = useState<SourceHealth[]>([]);
  const [showSources, setShowSources] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  // Cycle counts and the refresh control answer "is there anything worth
  // applying to right now?", which is only a question on Discover.
  const { pathname } = useLocation();
  const onDiscover = pathname.startsWith("/discover");

  useEffect(() => {
    api.cycles().then(setCycles).catch(() => {});
    api.sourceHealth().then(setHealth).catch(() => {});
  }, []);

  // Navigating is the menu's whole purpose, so it closes itself once you have.
  useEffect(() => setMenuOpen(false), [pathname]);

  // Escape closes it and puts focus back on the control that opened it --
  // otherwise a keyboard user lands at the top of the document instead.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const quarantined = health.filter((h) => h.is_quarantined || h.last_error).length;
  const okSources = health.filter((h) => h.last_success_at && !h.is_quarantined).length;

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1.5 rounded-lg text-sm font-500 transition-colors ${
      isActive
        ? "bg-white/[0.12] text-white"
        : "text-navy-300 hover:text-white hover:bg-white/[0.06]"
    }`;

  const cycleChips = cycles.map((c) => (
    <div
      key={c.term_label}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-2xs
                 font-medium border border-white/10 bg-white/[0.06] shrink-0"
      title={`${c.count} active postings for ${c.term_label}`}
    >
      <span className="text-navy-200">{c.term_label}</span>
      <span className="text-beacon-400 tabular-nums font-600">{c.count}</span>
    </div>
  ));

  const sourceButton = (
    // Clickable, because a count of broken feeds you cannot open is a problem
    // you learn to ignore rather than one you can fix.
    <button
      onClick={() => setShowSources(true)}
      className="flex items-center gap-1.5 text-2xs text-navy-300 shrink-0 rounded-md
                 px-1.5 py-1 hover:text-white hover:bg-white/[0.06] transition-colors"
      title="Which feeds are working, and which quietly stopped"
    >
      {/* Healthy is deliberately quiet -- a white dot, not a green light.
          Only trouble earns the beacon colour. */}
      <span className={`h-1.5 w-1.5 rounded-full ${quarantined ? "bg-beacon-400" : "bg-white/50"}`} />
      {/* "90 sources" read as the total. It is the healthy count out of 105,
          and the difference is the whole point of showing it. */}
      {okSources}/{health.length} sources
      {quarantined > 0 && <span className="text-beacon-400">· {quarantined} need attention</span>}
    </button>
  );

  return (
    // The hairline at the bottom edge is the lamp catching the top of the page.
    <header className="bg-navy-900 sticky top-0 z-30 shadow-[inset_0_-1px_0_rgba(239,132,32,0.45)]">
      <div className="px-4 sm:px-6 py-3 flex items-center gap-4">
        <div className="flex items-center gap-2.5 shrink-0">
          <Beacon />
          <div>
            <div className="text-sm font-700 text-white tracking-tight leading-none">Lighthouse</div>
            <div className="text-2xs text-navy-300 leading-none mt-0.5">
              internship command center
            </div>
          </div>
        </div>

        <nav className="hidden lg:flex items-center gap-1">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} className={navLinkClass}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex-1" />

        {onDiscover && (
          <div className="hidden lg:block">
            <RefreshButton onFinished={onRefreshed ?? (() => {})} />
          </div>
        )}

        <div className="hidden lg:block">{sourceButton}</div>

        <button
          ref={menuButton}
          onClick={() => setMenuOpen((v) => !v)}
          aria-expanded={menuOpen}
          aria-controls="lh-menu"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          className="lg:hidden shrink-0 rounded-lg p-2 -mr-1 text-navy-200 hover:text-white
                     hover:bg-white/[0.08] transition-colors"
        >
          {/* Two bars to an X. Drawn rather than an icon font so it inherits
              colour and needs no network request. */}
          <span className="block h-4 w-5 relative" aria-hidden="true">
            <span
              className={`absolute left-0 h-0.5 w-5 bg-current rounded transition-transform ${
                menuOpen ? "top-[7px] rotate-45" : "top-1"
              }`}
            />
            <span
              className={`absolute left-0 h-0.5 w-5 bg-current rounded transition-transform ${
                menuOpen ? "top-[7px] -rotate-45" : "top-[11px]"
              }`}
            />
          </span>
        </button>
      </div>

      {/* Cycle counts get their own row rather than competing with seven nav
          links for the leftovers. Squeezed into the main row they had about
          150px at 1440 -- enough for Winter 2027 and half of Spring, while
          Summer 2027, the cycle with four times the postings of either and the
          one actually being recruited for, was cut off with no scrollbar to
          say so. */}
      {onDiscover && cycles.length > 0 && (
        <div className="hidden lg:flex items-center gap-1.5 px-6 pb-2.5 overflow-x-auto no-scrollbar">
          <span className="text-2xs text-navy-400 shrink-0 mr-1">live postings</span>
          {cycleChips}
        </div>
      )}

      {/* The phone menu. Links first, because navigating is why it was opened;
          the cycle counts and refresh follow so Discover keeps its answer to
          "is there anything new" without a trip to a wider screen. */}
      {menuOpen && (
        <div id="lh-menu" className="lg:hidden border-t border-white/10 px-4 pb-3 pt-2">
          <nav className="flex flex-col gap-0.5">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `px-3 py-2.5 rounded-lg text-sm font-500 transition-colors ${
                    isActive
                      ? "bg-white/[0.12] text-white"
                      : "text-navy-300 hover:text-white hover:bg-white/[0.06]"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          {onDiscover && (
            <div className="mt-3 pt-3 border-t border-white/10 space-y-2.5">
              <div className="flex flex-wrap gap-1.5">{cycleChips}</div>
              <RefreshButton onFinished={onRefreshed ?? (() => {})} />
            </div>
          )}

          <div className="mt-3 pt-3 border-t border-white/10">{sourceButton}</div>
        </div>
      )}

      {showSources && <SourcePanel onClose={() => setShowSources(false)} />}
    </header>
  );
}

