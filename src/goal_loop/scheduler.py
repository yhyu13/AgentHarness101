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

    def __init__(self, runtime: GoalRuntime, runners: dict[str, Runner]) -> None:
        self._runtime = runtime
        self._runners = runners

    def active_goals(self) -> list:
        """Active goals worth scheduling, as ``Continuation`` objects."""
        return self._runtime.resume_all()

    def run_once(self) -> list[ScheduledRun]:
        """Run every active goal serially to terminal, collecting one result each."""
        results: list[ScheduledRun] = []
        for cont in self._runtime.resume_all():
            runner = self._runners.get(cont.thread_id)
            if runner is None:
                results.append(
                    ScheduledRun(
                        cont.thread_id, cont.goal.objective, SKIPPED, "no runner registered"
                    )
                )
                continue
            try:
                status = runner.run_until_terminal(cont.thread_id)
                results.append(ScheduledRun(cont.thread_id, cont.goal.objective, status.value))
            except Exception as exc:  # one crashed runner must not stop the batch
                results.append(
                    ScheduledRun(
                        cont.thread_id,
                        cont.goal.objective,
                        ERRORED,
                        f"{type(exc).__name__}: {exc}",
                    )
                )
        return results

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
            batches.append(self.run_once())
            cycles += 1
            if stop_after is not None and cycles >= stop_after:
                break
            if not self._runtime.resume_all():
                break
            sleep(0)
        return batches
