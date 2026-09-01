from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from goal_persistence import GoalRuntime, GoalStatus


class Runner(Protocol):
    """A thing that can drive one goal to a terminal status.

    ``GoalLoopRunner`` satisfies this structurally (its ``run_until_terminal`` accepts
    the thread id and optional budgets); the scheduler never needs more than that.
    """

    def run_until_terminal(self, thread_id: str, **kwargs) -> GoalStatus: ...


@dataclass(frozen=True)
class ScheduledRun:
    """The outcome of one goal processed by the scheduler.

    ``status`` is the terminal ``GoalStatus`` value, or one of two scheduler-only
    markers: ``"skipped"`` (no runner registered) and ``"errored"`` (the runner raised).
    """

    thread_id: str
    objective: str
    status: str
    summary: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "thread_id": self.thread_id,
            "objective": self.objective,
            "status": self.status,
            "summary": self.summary,
        }


SKIPPED = "skipped"
ERRORED = "errored"


class Scheduler:
    """Unattended scheduling (harness-skills survey §3: "night runs").

    Re-arms every active goal (``GoalRuntime.resume_all``), runs each serially to a
    terminal status, and renders a morning report. It routes runners and never calls an
    LLM; the only sleeps are an injectable no-op, so the whole cycle is deterministic and
    testable.
    """

    def __init__(
        self,
        runtime: GoalRuntime,
        runners: dict[str, Runner],
        quarantine_after: int = 3,
    ) -> None:
        self._runtime = runtime
        self._runners = runners
        self._quarantine_after = quarantine_after
        # Consecutive runner failures per thread (for poison-goal quarantine), and the
        # set of thread ids already made terminal this batch (for re-entrant resume).
        self._error_counts: dict[str, int] = {}
        self._handled: set[str] = set()

    @property
    def handled(self) -> set[str]:
        """Thread ids already driven terminal this batch; a re-entrant run skips them."""
        return self._handled

    def reset_batch(self) -> None:
        """Start a fresh batch: forget which goals were handled and clear error counts."""
        self._handled = set()
        self._error_counts = {}

    def active_goals(self) -> list:
        """Active goals worth scheduling, as ``Continuation`` objects."""
        return self._runtime.resume_all()

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff (seconds) for the ``attempt``-th retry."""
        return min(1.0, 0.5 * 2 ** (attempt - 1))

    def run_once(
        self,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 0,
    ) -> list[ScheduledRun]:
        """Run every active goal serially to terminal, collecting one result each.

        A transient runner failure is retried up to ``max_retries`` times with
        exponential backoff (``sleep`` injectable for determinism) before being recorded
        as ``errored``. A goal that errors ``quarantine_after`` consecutive times is set
        aside by the runtime so it cannot spin the schedule forever. Threads already in
        ``handled`` this batch are not reprocessed (re-entrant / post-restart resume).
        """
        results: list[ScheduledRun] = []
        for cont in self._runtime.resume_all():
            tid = cont.thread_id
            if tid in self._handled:
                continue
            runner = self._runners.get(tid)
            if runner is None:
                results.append(
                    ScheduledRun(tid, cont.goal.objective, SKIPPED, "no runner registered")
                )
                continue

            status_str: str | None = None
            summary = ""
            failure: Exception | None = None
            attempt = 0
            while status_str is None:
                try:
                    status = runner.run_until_terminal(tid)
                    status_str = status.value
                except Exception as exc:  # one crashed runner must not stop the batch
                    failure = exc
                    attempt += 1
                    if attempt > max_retries:
                        break
                    sleep(self._backoff(attempt))

            if status_str is None:  # retries exhausted -> errored
                status_str = ERRORED
                summary = f"{type(failure).__name__}: {failure}"
                self._note_error(tid, summary)
            else:
                self._note_success(tid)
                self._mark_handled(tid, status_str)
            results.append(ScheduledRun(tid, cont.goal.objective, status_str, summary))
        return results

    def _note_error(self, thread_id: str, summary: str) -> None:
        """Track a run failure; quarantine the goal once it exceeds the threshold."""
        count = self._error_counts.get(thread_id, 0) + 1
        self._error_counts[thread_id] = count
        if count >= self._quarantine_after:
            self._runtime.quarantine(thread_id, summary)
            self._handled.add(thread_id)
            self._error_counts.pop(thread_id, None)

    def _note_success(self, thread_id: str) -> None:
        """A clean run resets the consecutive-failure counter."""
        self._error_counts.pop(thread_id, None)

    def _mark_handled(self, thread_id: str, status_str: str) -> None:
        """Record a terminal goal so a re-entrant run does not reprocess it."""
        if status_str in (GoalStatus.COMPLETE.value, GoalStatus.BUDGET_LIMITED.value):
            self._handled.add(thread_id)

    def morning_report(self, runs: list[ScheduledRun]) -> str:
        """Render a one-page morning summary: counts plus one line per goal."""
        total = len(runs)

        def count(status: str) -> int:
            return sum(1 for r in runs if r.status == status)

        lines = [
            "# Morning report",
            (
                f"total={total} completed={count(GoalStatus.COMPLETE.value)} "
                f"blocked={count(GoalStatus.BLOCKED.value)} "
                f"errored={count(ERRORED)} skipped={count(SKIPPED)}"
            ),
        ]
        for run in runs:
            lines.append(f"- [{run.status}] {run.thread_id}: {run.objective}")
        return "\n".join(lines)

    def run_periodic(
        self,
        sleep: Callable[[float], None] = time.sleep,
        stop_after: Optional[int] = None,
    ) -> list[list[ScheduledRun]]:
        """Re-arm and run until no active goal remains (or ``stop_after`` cycles).

        Returns one batch (a ``list[ScheduledRun]``) per cycle. ``sleep`` is injectable
        so the cycle is deterministic under test; the caller decides the real cadence.
        """
        batches: list[list[ScheduledRun]] = []
        cycles = 0
        while True:
            self.reset_batch()
            batches.append(self.run_once())
            cycles += 1
            if stop_after is not None and cycles >= stop_after:
                break
            if not self._runtime.resume_all():
                break
            sleep(0)
        return batches
