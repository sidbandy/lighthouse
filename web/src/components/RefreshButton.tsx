import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { RefreshStatus } from "../api/types";

// Pull new postings on demand.
//
// The run happens in a worker thread on the backend and this polls it, because
// ~95 sources take the better part of a minute and no button should hold a
// request open that long. While it runs the operator gets the elapsed time
// rather than a spinner — a refresh that is genuinely taking 50 seconds should
// look like it is working, not like it has hung.

const POLL_MS = 3000;

export function RefreshButton({ onFinished }: { onFinished: () => void }) {
  const [status, setStatus] = useState<RefreshStatus | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [startError, setStartError] = useState<string | null>(null);
  const wasRunning = useRef(false);

  const poll = useCallback(async () => {
    try {
      const next = await api.refreshStatus();
      setStatus(next);
      // Only refetch the lanes on the transition out of running, so a finished
      // run updates the view exactly once instead of on every poll.
      if (wasRunning.current && !next.is_running) onFinished();
      wasRunning.current = next.is_running;
    } catch {
      /* the API being briefly unreachable is not worth surfacing here */
    }
  }, [onFinished]);

  useEffect(() => {
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => clearInterval(id);
  }, [poll]);

  useEffect(() => {
    if (!status?.is_running) return;
    const id = setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [status?.is_running]);

  const start = async () => {
    setElapsed(0);
    setStartError(null);
    wasRunning.current = true;
    try {
      setStatus(await api.startRefresh());
    } catch (e) {
      // Leaving wasRunning set would make the next poll read as a run that
      // finished and refetch the lanes for a run that never started.
      wasRunning.current = false;
      setStartError(String((e as Error).message ?? e));
    }
  };

  const running = status?.is_running ?? false;

  return (
    <div className="flex items-center gap-2 shrink-0">
      <button
        onClick={start}
        disabled={running}
        title={
          status?.summary ??
          "Fetch new postings from every source, including the ATS boards that carry full descriptions"
        }
        className="px-2.5 py-1 rounded-md text-2xs font-medium border border-white/10
                   bg-white/[0.06] text-navy-200 hover:text-white hover:bg-white/[0.12]
                   disabled:opacity-60 disabled:cursor-wait transition-colors"
      >
        {running ? `Refreshing… ${elapsed}s` : "Refresh postings"}
      </button>
      {!running && status?.summary && (
        <span className="text-2xs text-navy-400 hidden lg:inline" title={status.summary}>
          {status.created > 0 ? `+${status.created} new` : "up to date"}
        </span>
      )}
      {!running && (startError || status?.error) && (
        <span className="text-2xs text-beacon-400" title={startError ?? status?.error ?? undefined}>
          {startError ? "could not start" : "refresh failed"}
        </span>
      )}
    </div>
  );
}
