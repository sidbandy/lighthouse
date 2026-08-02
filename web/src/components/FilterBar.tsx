import type { RoleFamily, Season } from "../api/types";
import { roleLabel } from "../lib/format";

// The filters that decide whether the list is usable. Kept to the ones that
// actually change what the operator should look at: role, cycle, and whether to
// trust title-only matches.

export interface Filters {
  role: RoleFamily | null;
  season: Season | null;
  withDescriptionOnly: boolean;
}

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

export function FilterBar({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex gap-1">
        {ROLES.map((r) => (
          <button
            key={r}
            className={filters.role === r ? "btn-filter-on" : "btn-filter"}
            onClick={() => onChange({ ...filters, role: filters.role === r ? null : r })}
          >
            {roleLabel(r)}
          </button>
        ))}
      </div>

      <span className="w-px h-5 bg-navy-200 mx-1" />

      <div className="flex gap-1">
        {SEASONS.map((s) => (
          <button
            key={s.value}
            className={filters.season === s.value ? "btn-filter-on" : "btn-filter"}
            onClick={() =>
              onChange({ ...filters, season: filters.season === s.value ? null : s.value })
            }
          >
            {s.label}
          </button>
        ))}
      </div>

      <span className="w-px h-5 bg-navy-200 mx-1" />

      <button
        className={filters.withDescriptionOnly ? "btn-filter-on" : "btn-filter"}
        onClick={() => onChange({ ...filters, withDescriptionOnly: !filters.withDescriptionOnly })}
        title="Only postings with a full description, so match scores rest on real evidence"
      >
        {filters.withDescriptionOnly ? "✓ " : ""}Full descriptions only
      </button>
    </div>
  );
}
