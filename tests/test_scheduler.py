"""Unattended scheduling tests (harness-skills survey §3: "night runs").

The scheduler re-arms active goals (``resume_all``), runs each serially to a terminal
status (``run_until_terminal``), and produces a morning report. The LLM boundary is
untouched: the scheduler only routes existing runners and never calls a model. Runner
collaborators are stubbed in unit tests (isolating the scheduler's own ordering / skip /
error-isolation / report logic); one integration test wires a real ``GoalLoopRunner``
through the scheduler.
"""

from pathlib import Path

import pytest

from goal_loop import (
    AcceptanceCriterion,
    EchoMaker,
    GoalLoopRunner,
    GoalSpec,
    StaticChecker,
    StopCondition,
    Verdict,
)
from goal_loop.scheduler import ScheduledRun, Scheduler
from goal_persistence import GoalRuntime, GoalStatus, GoalStore


@pytest.fixture
def runtime(tmp_path: Path) -> GoalRuntime:
    return GoalRuntime(GoalStore(tmp_path / "goals.db"))


class _Runner:
    """A stub runner with a controllable ``run_until_terminal`` outcome."""

    def __init__(self, result: GoalStatus, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[str] = []

    def run_until_terminal(self, thread_id: str, **kwargs) -> GoalStatus:
        self.calls.append(thread_id)
        if self._error is not None:
            raise self._error
        return self._result


def _active(runtime: GoalRuntime, *thread_ids: str) -> GoalRuntime:
    for tid in thread_ids:
        runtime.create_goal(tid, f"objective for {tid}")
    return runtime


class TestScheduledRun:
    def test_round_trips(self) -> None:
        run = ScheduledRun("t1", "obj", "complete", "done")
        assert run.to_dict() == {
            "thread_id": "t1",
            "objective": "obj",
            "status": "complete",
            "summary": "done",
        }


class TestScheduler:
    def test_active_goals_returns_continuations(self, runtime: GoalRuntime) -> None:
        _active(runtime, "a", "b")
        conts = Scheduler(runtime, {}).active_goals()
        assert [c.thread_id for c in conts] == ["a", "b"]

    def test_run_once_runs_each_active_goal_in_order(self, runtime: GoalRuntime) -> None:
        _active(runtime, "a", "b", "c")
        ra, rb, rc = (
            _Runner(GoalStatus.COMPLETE),
            _Runner(GoalStatus.BLOCKED),
            _Runner(GoalStatus.COMPLETE),
        )
        scheduler = Scheduler(runtime, {"a": ra, "b": rb, "c": rc})
        results = scheduler.run_once()
        assert [r.thread_id for r in results] == ["a", "b", "c"]
        assert [r.status for r in results] == ["complete", "blocked", "complete"]

    def test_run_once_skips_goal_without_runner(self, runtime: GoalRuntime) -> None:
        _active(runtime, "a", "b")
        scheduler = Scheduler(runtime, {"a": _Runner(GoalStatus.COMPLETE)})
        results = scheduler.run_once()
        by_id = {r.thread_id: r for r in results}
        assert by_id["a"].status == "complete"
        assert by_id["b"].status == "skipped"

    def test_run_once_isolates_crashed_runner(self, runtime: GoalRuntime) -> None:
        _active(runtime, "a", "b")
        scheduler = Scheduler(
            runtime,
            {
                "a": _Runner(GoalStatus.COMPLETE, error=RuntimeError("boom")),
                "b": _Runner(GoalStatus.COMPLETE),
            },
        )
        results = scheduler.run_once()
        by_id = {r.thread_id: r for r in results}
        assert by_id["a"].status == "errored"
        assert "boom" in by_id["a"].summary
        assert by_id["b"].status == "complete"  # the crash did not stop the batch

    def test_morning_report_counts_and_lists(self) -> None:
        runs = [
            ScheduledRun("t1", "o1", "complete"),
            ScheduledRun("t2", "o2", "blocked"),
            ScheduledRun("t3", "o3", "errored", "boom"),
            ScheduledRun("t4", "o4", "skipped", "no runner"),
        ]
        report = Scheduler(GoalRuntime(GoalStore(":memory:")), {}).morning_report(runs)
        assert "total=4" in report
        assert "completed=1" in report
        assert "blocked=1" in report
        assert "errored=1" in report
        assert "skipped=1" in report
        assert "- [errored] t3" in report

    def test_run_periodic_stops_after_goals_terminal(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # A real runner that completes its goal on the first run: after one batch there
        # are no active goals left, so run_periodic must stop.
        runtime.create_goal("t1", "write a function")
        spec = GoalSpec(
            objective="write a function",
            acceptance_criteria=[AcceptanceCriterion("c1", "works", verify_command='py -c "pass"')],
            stop_conditions=[StopCondition(kind="max_rounds", value=10)],
        )
        runner = GoalLoopRunner(
            spec, runtime, EchoMaker("done"), StaticChecker(Verdict.PASS), state_dir=tmp_path
        )
        batches = Scheduler(runtime, {"t1": runner}).run_periodic(sleep=lambda s: None)
        assert len(batches) == 1
        assert batches[0][0].status == "complete"

    def test_run_periodic_respects_stop_after(self, runtime: GoalRuntime) -> None:
        _active(runtime, "t1")
        scheduler = Scheduler(runtime, {"t1": _Runner(GoalStatus.ACTIVE)})
        batches = scheduler.run_periodic(sleep=lambda s: None, stop_after=3)
        assert len(batches) == 3
