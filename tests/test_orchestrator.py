"""Multi-agent orchestration tests (harness-skills survey §4).

An orchestrator splits a goal among specialist sub-agents: a planner (goal -> steps),
an executor (one per step), and a reviewer (critiques the aggregated output). The
orchestrator is pure routing — it never calls an LLM — so "only mock the LLM boundary"
holds. ``make`` composes planner + executors into a ``Maker``; ``check`` is the
reviewer-as-``Checker``. Both plug straight into ``GoalLoopRunner``.
"""

from pathlib import Path

import pytest

from goal_loop import (
    AcceptanceCriterion,
    CheckerOutput,
    GoalLoopRunner,
    GoalSpec,
    MakerOutput,
    StopCondition,
    Verdict,
)
from goal_loop.orchestrator import Orchestrator, Plan
from goal_persistence import GoalRuntime, GoalStatus, GoalStore


@pytest.fixture
def runtime(tmp_path: Path) -> GoalRuntime:
    return GoalRuntime(GoalStore(tmp_path / "goals.db"))


def _spec() -> GoalSpec:
    return GoalSpec(
        objective="build a widget",
        acceptance_criteria=[AcceptanceCriterion("c1", "it works", verify_command='py -c "pass"')],
        stop_conditions=[StopCondition(kind="max_rounds", value=10)],
    )


class _Planner:
    def __init__(self, steps: list[str]) -> None:
        self._steps = steps

    def __call__(self, spec: GoalSpec) -> Plan:
        return Plan(objective=spec.objective, steps=self._steps)


class _Executor:
    def __init__(self, ok: bool = True, crash: bool = False) -> None:
        self._ok = ok
        self._crash = crash

    def __call__(self, spec: GoalSpec, plan: Plan, step: str) -> MakerOutput:
        if self._crash:
            raise RuntimeError("executor crashed")
        return MakerOutput(summary=f"executed {step}", ok=self._ok, tokens_used=1)


class _Reviewer:
    def __init__(self, verdict: Verdict = Verdict.PASS) -> None:
        self._verdict = verdict

    def __call__(self, spec: GoalSpec, output: MakerOutput) -> CheckerOutput:
        return CheckerOutput(verdict=self._verdict)


def _orch(planner, executor, reviewer) -> Orchestrator:
    return Orchestrator(planner=planner, executor=executor, reviewer=reviewer)


class TestOrchestratorMake:
    def test_fans_out_to_every_step(self) -> None:
        orch = _orch(_Planner(["a", "b", "c"]), _Executor(), _Reviewer())
        out = orch.make(_spec(), None, "steering")
        assert out.ok is True
        assert "executed a" in out.summary
        assert "executed b" in out.summary
        assert "executed c" in out.summary

    def test_ok_false_when_executor_reports_failure(self) -> None:
        orch = _orch(_Planner(["a"]), _Executor(ok=False), _Reviewer())
        out = orch.make(_spec(), None, "steering")
        assert out.ok is False

    def test_ok_false_when_executor_crashes(self) -> None:
        orch = _orch(_Planner(["a"]), _Executor(crash=True), _Reviewer())
        out = orch.make(_spec(), None, "steering")
        assert out.ok is False
        assert "crashed" in out.summary

    def test_empty_plan_is_not_ok(self) -> None:
        # No steps = no work done, so fail-closed rather than vacuously "ok".
        orch = _orch(_Planner([]), _Executor(), _Reviewer())
        out = orch.make(_spec(), None, "steering")
        assert out.ok is False


class TestOrchestratorCheck:
    def test_check_delegates_to_reviewer(self) -> None:
        orch = _orch(_Planner(["a"]), _Executor(), _Reviewer(Verdict.FAIL))
        out = orch.check(_spec(), MakerOutput(summary="x"))
        assert out.verdict == Verdict.FAIL


class TestOrchestratorInLoop:
    def test_orchestrator_runs_goal_loop_to_completion(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        orch = _orch(_Planner(["a"]), _Executor(), _Reviewer(Verdict.PASS))
        runner = GoalLoopRunner(_spec(), runtime, orch.make, orch.check, state_dir=tmp_path)
        assert runner.run("t1") == GoalStatus.COMPLETE
