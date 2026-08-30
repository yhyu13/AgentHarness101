"""Whole-system end-to-end test: every runtime layer composed in one real run.

Composes the eight layers the ``GoalLoopRunner`` actually wires together, plus the
three new components from the TDD work:

    faux_provider (scripted LLM maker) + goal_persistence (durable runtime)
    + goal_loop (runner) + sandbox (fail-closed @verify) + observability (trace)
    + hippocampus (memory) + world_verifier (verify-the-world) + checker.

Two scenarios prove the system end-to-end:

1. Happy path — the scripted maker reports the right artifact, the sandboxed
   ``@verify`` command re-reads it, the world verifier confirms byte-identical, and
   every layer leaves a real trace (trace replay, hippocampus trajectory, sandbox
   not blocked, faux queue drained). Ends ``complete``.

2. Adversarial path — the scripted maker reports "done" but the artifact on disk is
   WRONG, the ``@verify`` command is a fake ``exit 0``, and a lying checker says PASS.
   The world verifier is the only thing that prevents a false completion. Ends
   ``blocked``, never ``complete``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faux_provider import FauxMaker, FauxProvider
from goal_loop import (
    AcceptanceCriterion,
    CheckerOutput,
    GoalLoopRunner,
    GoalSpec,
    StaticChecker,
    StopCondition,
    Verdict,
)
from goal_loop.world_verifier import WorldCheck, WorldVerifier
from goal_persistence import GoalRuntime, GoalStatus, GoalStore
from hippocampus import Hippocampus, HippocampusStore
from observability import TraceLog
from sandbox import Sandbox

EXPECTED = "hello world"


def _verify_command(artifact: Path, expected: str) -> str:
    """A sandboxed ``@verify`` command that re-reads the artifact and compares it to
    ``expected`` through ``sys.argv``.

    The ``-c`` code contains no string literals and no shell metacharacters, so
    ``shlex.split`` round-trips it losslessly. The artifact path is forward-slashed
    and double-quoted so Windows backslashes survive ``shlex`` un-mangled.
    """
    code = (
        "import pathlib,sys;"
        "sys.exit(0 if pathlib.Path(sys.argv[1]).read_text()==sys.argv[2] else 1)"
    )
    path = str(artifact).replace("\\", "/")
    return f'py -c "{code}" "{path}" "{expected}"'


class _LyingChecker:
    """Always PASS regardless of machine or world evidence — the generator/evaluator
    separation breach that the world verifier must catch."""

    def __call__(self, spec, output):
        return CheckerOutput(verdict=Verdict.PASS, tokens_used=0)


def test_full_system_happy_path_completes(tmp_path: Path) -> None:
    # The "world" state the maker claims to have produced: the correct artifact.
    artifact = tmp_path / "out.txt"
    artifact.write_text(EXPECTED, encoding="utf-8")

    # goal 2: scripted LLM maker (one reply, consumed once).
    provider = FauxProvider(["wrote hello world"])
    maker = FauxMaker(provider, modified_files=[str(artifact)])

    # goal 3: world verifier re-reads the artifact byte-identical.
    world = WorldVerifier([WorldCheck(artifact, expected=EXPECTED)])

    sandbox = Sandbox(allowlist=["py"])
    trace = TraceLog(tmp_path / "trace.jsonl")
    hippocampus = Hippocampus(HippocampusStore(tmp_path / "memory"))

    spec = GoalSpec(
        objective="write a file containing hello world",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="c1",
                description="artifact equals hello world",
                verify_command=_verify_command(artifact, EXPECTED),
            )
        ],
        stop_conditions=[StopCondition(kind="max_rounds", value=5)],
    )

    runner = GoalLoopRunner(
        spec,
        GoalRuntime(GoalStore(tmp_path / "goals.db")),
        maker,
        StaticChecker(Verdict.PASS),
        state_dir=tmp_path,
        sandbox=sandbox,
        trace_log=trace,
        hippocampus=hippocampus,
        world_verifier=world,
    )

    status = runner.run("thread-1")

    # The completion itself proves the sandbox ran the @verify command (not blocked):
    # a blocked command would return code -1, fail the criterion, and never complete.
    assert status == GoalStatus.COMPLETE

    # observability: append-only trace recorded one full round, in order.
    assert [e.event_type for e in trace.replay()] == ["maker", "checker", "verification"]

    # memory: the round's trajectory is durable and replayable.
    replay = hippocampus.replay("thread-1-round-1")
    assert replay is not None
    assert [step.action for step in replay.trajectory.steps] == ["make"]

    # world: the artifact really is byte-identical on disk.
    assert artifact.read_bytes() == EXPECTED.encode("utf-8")

    # faux: the scripted LLM was consumed exactly once, queue drained.
    assert provider.call_count == 1
    assert provider.get_pending_response_count() == 0


def test_full_system_fake_exit0_wrong_artifact_never_completes(tmp_path: Path) -> None:
    # The world contradicts the maker's self-report: wrong content on disk.
    artifact = tmp_path / "out.txt"
    artifact.write_text("wrong content", encoding="utf-8")

    # 4 replies: round 1 counts as progress (the fake exit-0 "satisfies" the
    # criterion once), then three no-progress strikes trip the blocked audit
    # (GoalRuntime.BLOCKED_THRESHOLD == 3).
    provider = FauxProvider(["wrote hello world"] * 4)
    maker = FauxMaker(provider, modified_files=[str(artifact)])

    world = WorldVerifier([WorldCheck(artifact, expected=EXPECTED)])
    sandbox = Sandbox(allowlist=["py"])
    trace = TraceLog(tmp_path / "trace.jsonl")
    hippocampus = Hippocampus(HippocampusStore(tmp_path / "memory"))

    spec = GoalSpec(
        objective="write a file containing hello world",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="c1",
                description="artifact equals hello world",
                verify_command='py -c "pass"',  # fake exit-0: checks nothing
            )
        ],
        stop_conditions=[StopCondition(kind="max_rounds", value=10)],
    )

    runner = GoalLoopRunner(
        spec,
        GoalRuntime(GoalStore(tmp_path / "goals.db")),
        maker,
        _LyingChecker(),
        state_dir=tmp_path,
        sandbox=sandbox,
        trace_log=trace,
        hippocampus=hippocampus,
        world_verifier=world,
    )

    status = runner.run("thread-1")

    # The world verifier is the only defense: exit-0 command + lying PASS checker
    # would otherwise complete. It must end blocked, never complete.
    assert status == GoalStatus.BLOCKED
    assert status != GoalStatus.COMPLETE

    # The wrong bytes were never "corrected" — the world verifier observed reality.
    assert artifact.read_bytes() == b"wrong content"

    # faux consumed exactly 4 scripted replies (4 rounds), and observability recorded
    # 4 maker calls — one per round, so the loop genuinely retried, it did not
    # declare victory on a fake exit-0.
    assert provider.call_count == 4
    assert [e.event_type for e in trace.replay()] == ["maker", "checker", "verification"] * 4
