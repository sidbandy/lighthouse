import { useEffect, useRef, useState } from "react";
import type { EmploymentType, RoleFamily, Season, Sponsorship } from "../api/types";
import { roleLabel } from "../lib/format";

// The filters that decide whether the list is usable.
//
// Sponsorship and location are first-class rather than buried: a posting the
// operator cannot legally take is worse than no posting, because it costs
// attention before it costs an application.
//
// Everything here is plain text until selected — eighteen bordered pills read
// louder than the postings they filter.

export interface Filters {
  role: RoleFamily | null;
  season: Season | null;
  employmentType: EmploymentType | null;
  sponsorship: Sponsorship | null;
  /** Raw text, e.g. "TX, NY". Parsed to two-letter codes on the way out. */
  states: string;
  remoteOnly: boolean;
  postedWithinDays: number | null;
  search: string;
  withDescriptionOnly: boolean;
}

export const EMPTY_FILTERS: Filters = {
  role: null,
  season: null,
  employmentType: null,
  sponsorship: null,
  states: "",
  remoteOnly: false,
  postedWithinDays: null,
  search: "",
  withDescriptionOnly: false,
};

export const ROLES: RoleFamily[] = [
  "swe",
  "ai_ml",
  "data",
  "quant",
  "hardware",
  "security",
  "product",
  "design",
  "finance",
  "consulting",
  "business",
  "marketing",
  "mechanical",
  "science",
];

const SEASONS: { value: Season; label: string }[] = [
  { value: "fall", label: "Fall" },
  { value: "winter", label: "Winter" },
  { value: "spring", label: "Spring" },
  { value: "summer", label: "Summer" },
];

const EMPLOYMENT: { value: EmploymentType; label: string }[] = [
  { value: "internship", label: "Internship" },
  { value: "new_grad", label: "New grad" },
];

// The three states the data actually carries, named as the posting means them.
// No "eligible for me" shorthand: that would hide the posting's own claim
// behind an inference about the operator.
const SPONSORSHIP: { value: Sponsorship; label: string; title: string }[] = [
  { value: "offers", label: "Sponsors", title: "The posting says it offers visa sponsorship" },
  {
    value: "does_not_offer",
    label: "No sponsorship",
    title: "The posting says it does not offer sponsorship",
  },
  {
    value: "citizenship_required",
    label: "Citizens only",
    title: "The posting requires US citizenship or a security clearance",
  },
];

const POSTED_WITHIN: { value: number; label: string }[] = [
  { value: 7, label: "7d" },
  { value: 14, label: "14d" },
  { value: 30, label: "30d" },
];

/** "tx, ny" -> ["TX", "NY"]. Anything that is not a two-letter code is dropped
 *  rather than sent, so a half-typed "Tex" does not empty the list. */
export function parseStates(raw: string): string[] {
  return raw
    .split(/[,\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter((s) => /^[A-Z]{2}$/.test(s));
}

export function FilterBar({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
}) {
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    onChange({ ...filters, [key]: value });

  /** Click the selected option again to clear it. */
  const toggle = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    set(key, (filters[key] === value ? null : value) as Filters[K]);

  const active =
    filters.role !== null ||
    filters.season !== null ||
    filters.employmentType !== null ||
    filters.sponsorship !== null ||
    filters.states !== "" ||
    filters.remoteOnly ||
    filters.postedWithinDays !== null ||
    filters.search !== "" ||
    filters.withDescriptionOnly;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1">
        {ROLES.map((r) => (
          <button
            key={r}
            className={filters.role === r ? "btn-filter-on" : "btn-filter"}
            onClick={() => toggle("role", r)}
          >
            {roleLabel(r)}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-1">
        {EMPLOYMENT.map((e) => (
          <button
            key={e.value}
            className={filters.employmentType === e.value ? "btn-filter-on" : "btn-filter"}
            onClick={() => toggle("employmentType", e.value)}
          >
            {e.label}
          </button>
        ))}

        <Divider />

        {SEASONS.map((s) => (
          <button
            key={s.value}
            className={filters.season === s.value ? "btn-filter-on" : "btn-filter"}
            onClick={() => toggle("season", s.value)}
          >
            {s.label}
          </button>
        ))}

        <Divider />

        {SPONSORSHIP.map((s) => (
          <button
            key={s.value}
            title={s.title}
            className={filters.sponsorship === s.value ? "btn-filter-on" : "btn-filter"}
            onClick={() => toggle("sponsorship", s.value)}
          >
            {s.label}
          </button>
        ))}

        <Divider />

        <button
          className={filters.remoteOnly ? "btn-filter-on" : "btn-filter"}
          onClick={() => set("remoteOnly", !filters.remoteOnly)}
        >
          Remote
        </button>
        <StateInput value={filters.states} onCommit={(v) => set("states", v)} />

        <Divider />

        <span className="text-2xs text-navy-400 pl-1">posted</span>
        {POSTED_WITHIN.map((p) => (
          <button
            key={p.value}
            className={filters.postedWithinDays === p.value ? "btn-filter-on" : "btn-filter"}
            onClick={() => toggle("postedWithinDays", p.value)}
            title={`Posted within the last ${p.value} days. Rolling review closes roles fast.`}
          >
            {p.label}
          </button>
        ))}

        <Divider />

        <button
          className={filters.withDescriptionOnly ? "btn-filter-on" : "btn-filter"}
          onClick={() => set("withDescriptionOnly", !filters.withDescriptionOnly)}
          title="Only postings with a full description, so match scores rest on real evidence"
        >
          {filters.withDescriptionOnly ? "✓ " : ""}Full descriptions
        </button>

        <SearchInput value={filters.search} onCommit={(v) => set("search", v)} />

        {active && (
          <button
            className="btn-filter text-navy-400 hover:text-bad ml-auto"
            onClick={() => onChange(EMPTY_FILTERS)}
          >
            Clear all
          </button>
        )}
      </div>
    </div>
  );
}

function Divider() {
  return <span className="w-px h-4 bg-navy-200 mx-1.5 shrink-0" />;
}

/** Commits on a pause rather than per keystroke — each change refetches and
 *  rescores the whole list. */
function useDebouncedCommit(value: string, onCommit: (v: string) => void, ms = 350) {
  const [draft, setDraft] = useState(value);
  const committed = useRef(value);

  useEffect(() => {
    if (value !== committed.current) {
      committed.current = value;
      setDraft(value);
    }
  }, [value]);

  useEffect(() => {
    if (draft === committed.current) return;
    const timer = setTimeout(() => {
      committed.current = draft;
      onCommit(draft);
    }, ms);
    return () => clearTimeout(timer);
  }, [draft, ms, onCommit]);

  return [draft, setDraft] as const;
}

function SearchInput({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const [draft, setDraft] = useDebouncedCommit(value, onCommit);
  return (
    <input
      type="search"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      placeholder="title or company"
      className="text-2xs bg-white border border-navy-200 rounded px-2 py-1 w-40 text-navy-700
                 placeholder:text-navy-300 hover:border-navy-300 focus:border-beacon-500 outline-none"
    />
  );
}

function StateInput({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const [draft, setDraft] = useDebouncedCommit(value, onCommit);
  const parsed = parseStates(draft);
  const partial = draft.trim() !== "" && parsed.length === 0;
  return (
    <input
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      placeholder="TX, NY"
      title="Two-letter state codes, comma separated"
      className={`text-2xs bg-white border rounded px-2 py-1 w-20 text-navy-700 uppercase
                  placeholder:text-navy-300 placeholder:normal-case outline-none
                  focus:border-beacon-500 ${partial ? "border-warn/50" : "border-navy-200 hover:border-navy-300"}`}
    />
  );
}
