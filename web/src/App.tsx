import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { LaneBucket } from "./api/types";
import { CorpusPage } from "./components/CorpusPage";
import { FilterBar, type Filters } from "./components/FilterBar";
import { Header, type View } from "./components/Header";
import { LaneColumn } from "./components/LaneColumn";
import { PostingDrawer } from "./components/PostingDrawer";
import { ResumeCheck } from "./components/ResumeCheck";
import { TrackBoard } from "./components/TrackBoard";

const EMPTY_FILTERS: Filters = { role: null, season: null, withDescriptionOnly: false };

export default function App() {
  const [view, setView] = useState<View>("discover");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [lanes, setLanes] = useState<LaneBucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .discover({
        role_family: filters.role ? [filters.role] : undefined,
        season: filters.season ? [filters.season] : undefined,
        with_description_only: filters.withDescriptionOnly,
        per_lane: 20,
      })
      .then(setLanes)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [filters]);

  useEffect(() => load(), [load]);

  const total = lanes.reduce((n, l) => n + l.count, 0);

  if (view !== "discover") {
    return (
      <div className="min-h-full flex flex-col">
        <Header view={view} onView={setView} />
        {view === "corpus" ? <CorpusPage /> : view === "track" ? <TrackBoard /> : <ResumeCheck />}
      </div>
    );
  }

  return (
    <div className="min-h-full flex flex-col">
      <Header view={view} onView={setView} />

      <div className="px-6 py-4 border-b border-navy-200/60">
        <FilterBar filters={filters} onChange={setFilters} />
      </div>

      <main className="flex-1 px-6 py-5">
        {loading && <CenteredNote>Scoring postings against your corpus…</CenteredNote>}

        {error && (
          <CenteredNote>
            <p className="text-bad">Could not reach the API.</p>
            <p className="text-2xs text-navy-500 mt-1">
              Is the backend running on :8077? <code className="text-navy-600">make dev</code>
            </p>
          </CenteredNote>
        )}

        {!loading && !error && total === 0 && (
          <CenteredNote>
            <p>No postings match these filters.</p>
            <p className="text-2xs text-navy-500 mt-1">
              Try clearing filters, or run an ingest to refresh the list.
            </p>
          </CenteredNote>
        )}

        {!loading && !error && total > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 max-w-[1400px] mx-auto">
            {lanes.map((bucket) => (
              <LaneColumn key={bucket.lane} bucket={bucket} onOpen={setOpenId} />
            ))}
          </div>
        )}
      </main>

      <PostingDrawer id={openId} onClose={() => setOpenId(null)} />
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
