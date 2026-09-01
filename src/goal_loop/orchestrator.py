from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from goal_loop.models import CheckerOutput, GoalSpec, MakerOutput


@dataclass(frozen=True)
class Plan:
    """A planner's decomposition of a goal into ordered steps."""

    objective: str
    steps: list[str]


class Planner(Protocol):
    """Turn a goal spec into a step plan."""

    def __call__(self, spec: GoalSpec) -> Plan: ...


class Executor(Protocol):
    """Execute one planned step, reporting a ``MakerOutput``."""

    def __call__(self, spec: GoalSpec, plan: Plan, step: str) -> MakerOutput: ...


class Reviewer(Protocol):
    """Independently critique the aggregated output as a ``CheckerOutput``."""

    def __call__(self, spec: GoalSpec, output: MakerOutput) -> CheckerOutput: ...


class Orchestrator:
    """Split a goal among N specialist sub-agents (harness-skills survey §4).

    ``make`` is the maker half: plan the goal, fan out one executor per step, and
    aggregate into a single ``MakerOutput`` whose ``ok`` is the conjunction of every
    executor's ``ok`` (fail-closed: a crash or an empty plan is ``ok=False``).
    ``check`` is the checker half: the reviewer critiques that output.

    Because ``make`` and ``check`` match the ``Maker`` / ``Checker`` protocol shapes,
    an orchestrator plugs straight into ``GoalLoopRunner`` — no loop change needed.
    """

    def __init__(self, planner: Planner, executor: Executor, reviewer: Reviewer) -> None:
        self._planner = planner
        self._executor = executor
        self._reviewer = reviewer

    def make(self, spec: GoalSpec, state, steering: str) -> MakerOutput:
        plan = self._planner(spec)
        outputs: list[MakerOutput] = []
        errors: list[str] = []
        for step in plan.steps:
            try:
                outputs.append(self._executor(spec, plan, step))
            except Exception as exc:  # a crashed executor is no-progress, never a crash
                errors.append(f"{step}: {type(exc).__name__}: {exc}")

        ok = not errors and bool(outputs) and all(o.ok for o in outputs)
        summary = "; ".join(
            [f"plan: {len(plan.steps)} steps"]
            + [o.summary for o in outputs]
            + (["errors: " + "; ".join(errors)] if errors else [])
        )
        tokens = sum(o.tokens_used for o in outputs)
        return MakerOutput(
            summary=summary,
            ok=ok,
            tokens_used=tokens,
            self_verification="orchestrated planner -> executor(s) -> reviewer",
        )

    def check(self, spec: GoalSpec, output: MakerOutput) -> CheckerOutput:
        return self._reviewer(spec, output)
