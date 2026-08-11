import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api } from "./api/client";
import type { LaneBucket } from "./api/types";
import { CorpusPage } from "./components/CorpusPage";
import { EMPTY_FILTERS, FilterBar, parseStates, type Filters } from "./components/FilterBar";
import { Header } from "./components/Header";
import { LaneColumn } from "./components/LaneColumn";
import { NetworkPage } from "./components/NetworkPage";
import { PracticePage } from "./components/PracticePage";
import { PostingDrawer } from "./components/PostingDrawer";
import { ResumeCheck } from "./components/ResumeCheck";
import { StudyPage } from "./components/StudyPage";
import { TrackBoard } from "./components/TrackBoard";

// Every page has a URL. Not for its own sake: the posting window is the thing
// worth linking to — it is where the decision gets made — and once there are
// company pages, study plans and mock sessions there is no version of this that
// works off a single `view` string.

// How many postings each lane shows, and how much "show more" adds. Twenty is
// about a screen; the market behind it is thousands.
const PER_LANE_STEP = 20;

export default function App() {
  return (
    <div className="min-h-full flex flex-col">
      <Routes>
        <Route path="/discover/:postingId?" element={<Discover />} />
        <Route
          path="/applications"
          element={
            <>
              <Header />
              <TrackBoard />
            </>
          }
        />
        <Route
          path="/network"
          element={
            <>
              <Header />
              <NetworkPage />
            </>
          }
        />
        <Route
          path="/study"
          element={
            <>
              <Header />
              <StudyPage />
            </>
          }
        />
        <Route
          path="/practice"
          element={
            <>
              <Header />
              <PracticePage />
            </>
          }
        />
        <Route
          path="/corpus"
          element={
            <>
              <Header />
              <CorpusPage />
            </>
          }
        />
        <Route
          path="/resume"
          element={
            <>
              <Header />
              <ResumeCheck />
            </>
          }
        />
        <Route path="*" element={<Navigate to="/discover" replace />} />
      </Routes>
    </div>
  );
}

function Discover() {
  const { postingId } = useParams();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [lanes, setLanes] = useState<LaneBucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // How deep into each lane to go. There are thousands of applyable postings
  // and the lanes are capped, so without this the list stops at the cap and
  // there is no way to tell that from the end of the market.
  const [perLane, setPerLane] = useState(PER_LANE_STEP);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const states = parseStates(filters.states);
    api
      .discover({
        role_family: filters.role ? [filters.role] : undefined,
        season: filters.season ? [filters.season] : undefined,
        employment_type: filters.employmentType ? [filters.employmentType] : undefined,
        sponsorship: filters.sponsorship ? [filters.sponsorship] : undefined,
        state: states.length ? states : undefined,
        search: filters.search.trim() || undefined,
        remote_only: filters.remoteOnly || undefined,
        posted_within_days: filters.postedWithinDays ?? undefined,
        with_description_only: filters.withDescriptionOnly,
        per_lane: perLane,
      })
      .then(setLanes)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [filters, perLane]);

  useEffect(() => load(), [load]);

  // A new query starts from the top again.
  useEffect(() => setPerLane(PER_LANE_STEP), [filters]);

  const total = lanes.reduce((n, l) => n + l.count, 0);
  const moreAvailable = lanes.some((l) => l.has_more);
  // Every score is 0 against an empty corpus. Without saying so, the page reads
  // as "you match nothing" when it means "you haven't told me anything yet" —
  // and that is a verdict the app has no business implying.
  const corpusEmpty =
    total > 0 && lanes.every((l) => l.postings.every((p) => p.match.corpus_size === 0));

  return (
    <>
      <Header onRefreshed={load} />

      <div className="px-6 py-4 border-b border-navy-200/60">
        <FilterBar filters={filters} onChange={setFilters} />
      </div>

      <main className="flex-1 px-6 py-5">
        {corpusEmpty && <EmptyCorpusBanner />}

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
          <div className="max-w-[1400px] mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
              {lanes.map((bucket) => (
                <LaneColumn
                  key={bucket.lane}
                  bucket={bucket}
                  onOpen={(id) => navigate(`/discover/${id}`)}
                />
              ))}
            </div>

            <div className="mt-6 text-center">
              {moreAvailable ? (
                <button
                  onClick={() => setPerLane((n) => n + PER_LANE_STEP)}
                  className="btn-toggle text-xs"
                >
                  Show more in each lane
                </button>
              ) : (
                <p className="text-2xs text-navy-400">
                  That is everything matching these filters. Narrow them, or widen the cycle.
                </p>
              )}
            </div>
          </div>
        )}
      </main>

      <PostingDrawer
        id={postingId ?? null}
        onClose={() => navigate("/discover")}
        onTrackedChange={load}
      />
    </>
  );
}

/** The first thing a new user should read, and the only thing worth doing
 *  before anything else on this page means anything. */
function EmptyCorpusBanner() {
  return (
    <div className="card p-4 mb-5 border-beacon-500/30 bg-beacon-glow max-w-[1400px] mx-auto">
      <div className="flex items-start gap-3">
        <span className="text-beacon-600 text-sm mt-0.5">→</span>
        <div className="flex-1">
          <p className="text-sm font-600 text-navy-900">
            Every score below is 0 because your corpus is empty.
          </p>
          <p className="text-xs text-navy-600 mt-1 leading-relaxed max-w-2xl">
            That is not a judgement about these postings — Lighthouse has nothing of yours to
            compare them against yet. Add a résumé and a couple of projects and the same list
            re-sorts around what you can actually evidence.
          </p>
          <Link to="/corpus" className="btn-primary text-xs mt-2.5 inline-flex">
            Set up your corpus
          </Link>
        </div>
      </div>
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
