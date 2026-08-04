"""Running an ingest in the background, with a status the UI can poll.

The synchronous endpoint is right for the CLI and for tests, but a refresh
button cannot hold an HTTP connection open while ~95 sources are fetched. This
wraps a run in a worker thread and exposes the one piece of state the UI needs:
is it running, and what happened last time.

Deliberately in-memory and single-slot. A second refresh while one is in flight
is refused rather than queued — two concurrent runs would race on the same
dedup keys for no benefit, and the operator pressing a button twice means
"refresh", not "refresh twice". State is lost on restart, which is correct:
"currently running" cannot survive the process that was running it, and the
durable record of what happened lives in ``source_health`` either way.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from ..core.db import session_scope
from .pipeline import run_ingest

log = logging.getLogger(__name__)


@dataclass(slots=True)
class RunState:
    """What the refresh button needs to render."""

    is_running: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: str | None = None
    error: str | None = None
    created: int = 0
    updated: int = 0
    sources_ok: int = 0
    sources_failed: int = 0

    def snapshot(self) -> RunState:
        return RunState(**{f: getattr(self, f) for f in self.__slots__})


class _Runner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = RunState()

    @property
    def state(self) -> RunState:
        with self._lock:
            return self._state.snapshot()

    def start(self, *, max_tier: int) -> tuple[bool, RunState]:
        """Begin a run. Returns ``(started, state)``.

        ``started`` is False when one is already in flight, which the caller
        should surface as "already refreshing" rather than as an error.
        """
        with self._lock:
            if self._state.is_running:
                return False, self._state.snapshot()
            self._state = RunState(is_running=True, started_at=datetime.now(UTC))
            snapshot = self._state.snapshot()

        thread = threading.Thread(
            target=self._run, args=(max_tier,), name="lighthouse-ingest", daemon=True
        )
        thread.start()
        return True, snapshot

    def _run(self, max_tier: int) -> None:
        finished = RunState(is_running=False, started_at=self.state.started_at)
        try:
            # Its own session: the request that started this is long gone, and
            # a request-scoped session would be closed underneath us.
            with session_scope() as session:
                report = run_ingest(session, max_tier=max_tier)
            finished.summary = report.summary()
            finished.created = report.created
            finished.updated = report.updated
            finished.sources_ok = sum(1 for s in report.sources if s.ok)
            finished.sources_failed = sum(1 for s in report.sources if not s.ok)
        except Exception as exc:  # a failed refresh must not kill the worker
            log.exception("ingest run failed")
            finished.error = f"{type(exc).__name__}: {exc}"
        finally:
            finished.finished_at = datetime.now(UTC)
            with self._lock:
                self._state = finished


_runner = _Runner()


def start(*, max_tier: int = 2) -> tuple[bool, RunState]:
    return _runner.start(max_tier=max_tier)


def status() -> RunState:
    return _runner.state


def _reset_for_tests() -> None:
    global _runner
    _runner = _Runner()
