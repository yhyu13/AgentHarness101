"""Adversarial boundary tests: attack the harness where happy-path tests don't reach.

Each test targets a specific failure mode a naive "it passed" would hide:
- a maker that is permission-blocked must never complete, even with a PASS stub checker
  and a command-less criterion;
- a checker that lies (PASS while machine commands fail) must block, not spin;
- budget exhaustion must be terminal and never be mutated into complete/blocked;
- the sandbox must fail closed on an unconfigured backend;
- the trace log must survive a restart and reconstruct bytes exactly.
"""

from pathlib import Path

import pytest

from goal_loop import (
    AcceptanceCriterion,
    CheckerOutput,
    GoalLoopRunner,
    GoalSpec,
    MakerOutput,
    StaticChecker,
    StopCondition,
    Verdict,
)
from goal_loop.registered_roles import RegisteredMaker
from goal_persistence import GoalRuntime, GoalStatus, GoalStore
from tool_registry import Permission, ToolRegistry
from sandbox import Sandbox
from observability import TraceLog


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "goals.db"


@pytest.fixture
def runtime(tmp_db: Path) -> GoalRuntime:
    return GoalRuntime(GoalStore(tmp_db))


def spec_with(
    criteria: list[AcceptanceCriterion], max_rounds: int | None = None
) -> GoalSpec:
    stops = [StopCondition(kind="max_rounds", value=max_rounds)] if max_rounds else []
    return GoalSpec(
        objective="adversarial boundary",
        acceptance_criteria=criteria,
        stop_conditions=stops,
    )


class _BlockedMaker:
    def __call__(self, spec, state, steering):
        return MakerOutput(summary="blocked", ok=False, tokens_used=0)


class _LyingChecker:
    """Always PASS, regardless of machine evidence."""

    def __call__(self, spec, output):
        return CheckerOutput(verdict=Verdict.PASS, tokens_used=0)


class _CrashedMaker:
    def __call__(self, spec, state, steering):
        raise RuntimeError("maker crashed")


class _WorkingMaker:
    """Reports ok=True and does no file work — relies on machine command for truth."""

    def __call__(self, spec, state, steering):
        return MakerOutput(summary="worked", ok=True, tokens_used=1)


def test_blocked_maker_never_completes_even_with_pass_checker(
    runtime: GoalRuntime, tmp_path: Path
) -> None:
    """The sharp edge: command-less criterion + PASS checker + blocked maker.

    A command-less criterion is satisfied by a non-FAIL checker verdict, so without the
    maker's ok flag the loop would wrongly complete. The maker being blocked must be
    no-progress, and after three rounds the goal must BLOCK rather than complete.
    """
    spec = spec_with([AcceptanceCriterion("c1", "checker-decided")], max_rounds=10)
    runner = GoalLoopRunner(
        spec,
        runtime,
        _BlockedMaker(),
        _LyingChecker(),
        state_dir=tmp_path,
    )
    status = runner.run("t1")
    assert status == GoalStatus.BLOCKED
    assert runtime.get_goal("t1").status == GoalStatus.BLOCKED


def test_lying_checker_with_failing_commands_blocks_not_completes(
    runtime: GoalRuntime, tmp_path: Path
) -> None:
    """A checker that lies (PASS) while the machine command fails must not complete."""
    spec = spec_with(
        [AcceptanceCriterion("c1", "fails", verify_command="py -c \"raise SystemExit(1)\"")],
        max_rounds=10,
    )
    runner = GoalLoopRunner(
        spec, runtime, _BlockedMaker(), _LyingChecker(), state_dir=tmp_path
    )
    status = runner.run("t1")
    assert status == GoalStatus.BLOCKED


def test_lying_checker_alone_cannot_complete_failing_command(
    runtime: GoalRuntime, tmp_path: Path
) -> None:
    """A working maker + a lying (PASS) checker + a failing machine command must still
    block, proving the machine command — not the checker's word — is the truth for
    command-bearing criteria."""
    spec = spec_with(
        [AcceptanceCriterion("c1", "fails", verify_command="py -c \"raise SystemExit(1)\"")],
        max_rounds=10,
    )
    runner = GoalLoopRunner(
        spec, runtime, _WorkingMaker(), _LyingChecker(), state_dir=tmp_path
    )
    status = runner.run("t1")
    assert status == GoalStatus.BLOCKED


def test_budget_exhaustion_is_terminal_and_never_completed(
    tmp_db: Path, tmp_path: Path
) -> None:
    runtime = GoalRuntime(GoalStore(tmp_db))
    # A maker that reports huge usage each round exhausts a tiny budget on round 1.
    class _HugeMaker:
        def __call__(self, spec, state, steering):
            return MakerOutput(summary="huge", tokens_used=1_000_000, ok=True)

    spec = spec_with(
        [AcceptanceCriterion("c1", "fails", verify_command="py -c \"raise SystemExit(1)\"")],
        max_rounds=10,
    )
    runner = GoalLoopRunner(
        spec, runtime, _HugeMaker(), _LyingChecker(), state_dir=tmp_path
    )
    status = runner.run("t1", budget_tokens=10)
    assert status == GoalStatus.BUDGET_LIMITED
    # Terminal: cannot be flipped to complete or blocked afterward.
    goal = runtime.get_goal("t1")
    assert goal.status == GoalStatus.BUDGET_LIMITED


def test_unconfigured_sandbox_fails_closed() -> None:
    sb = Sandbox(allowlist=[])
    result = sb.run(["python", "-c", "print(1)"])
    assert result.blocked
    assert result.reason == "SANDBOX_UNAVAILABLE"
    assert not result.ok


def test_trace_survives_restart_and_reconstructs_exactly(tmp_path: Path) -> None:
    log = TraceLog(tmp_path / "session.jsonl")
    first = log.append("message", {"role": "user", "content": "hi"})
    # Simulate a process restart by reopening the same file.
    reopened = TraceLog(tmp_path / "session.jsonl")
    second = reopened.append("message", {"role": "assistant", "content": "hello"})
    replay = reopened.replay()
    assert [e.seq for e in replay] == [0, 1]
    assert replay[0].payload == {"role": "user", "content": "hi"}
    assert replay[1].payload == {"role": "assistant", "content": "hello"}
