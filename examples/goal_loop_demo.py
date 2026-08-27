"""End-to-end demo of the goal loop harness.

The demo has a maker that only produces the required artifact on its second attempt,
and a checker that runs a real subprocess to verify that artifact. The loop must
therefore fail its first round and pass its second — proving the loop actually runs and
verifies, instead of stamping a pre-existing success.

Run:
    py -3 examples/goal_loop_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from goal_loop import (
    AcceptanceCriterion,
    CheckerOutput,
    CommandVerifier,
    GoalLoopRunner,
    GoalSpec,
    MakerOutput,
    Scope,
    StaticChecker,
    StopCondition,
    Verdict,
)
from goal_persistence import GoalRuntime, GoalStatus, GoalStore


class ArtifactMaker:
    """Writes the required file on its second call, then reports it done."""

    def __init__(self, artifact: Path) -> None:
        self._artifact = artifact
        self._calls = 0

    def __call__(self, spec, state, steering: str) -> MakerOutput:
        self._calls += 1
        if self._calls < 2:
            return MakerOutput(
                summary="first attempt: artifact not yet written",
                modified_files=[],
                self_verification="nothing to verify yet",
                tokens_used=12,
            )
        self._artifact.write_text("ok\n", encoding="utf-8")
        return MakerOutput(
            summary="second attempt: wrote the required artifact",
            modified_files=[str(self._artifact)],
            self_verification="artifact exists (self-report, untrusted)",
            tokens_used=24,
        )


class ArtifactChecker:
    """Independently verifies the artifact by reading it in a subprocess."""

    def __init__(self, artifact: Path) -> None:
        self._artifact = artifact

    def __call__(self, spec, output: MakerOutput) -> CheckerOutput:
        # A separate python process reads the file, so the checker does not trust the
        # maker's own claim that it wrote it. The check asserts the actual content, so
        # a file that exists with the wrong bytes fails rather than passing.
        result = CommandVerifier().run(
            f"py -c \"assert open({str(self._artifact)!r}).read().strip() == 'ok'\""
        )
        verdict = Verdict.PASS if result.ok else Verdict.FAIL
        return CheckerOutput(verdict=verdict, command_results=[result], tokens_used=8)


def main() -> None:
    db = Path(__file__).with_name("goal_loop_demo.db")
    if db.exists():
        db.unlink()
    state_dir = Path(__file__).with_name("goal_loop_demo_state")
    artifact = Path(__file__).with_name("goal_loop_demo_artifact.txt")
    if artifact.exists():
        artifact.unlink()

    spec = GoalSpec(
        objective="Produce a verified artifact",
        acceptance_criteria=[
            AcceptanceCriterion(
                "c1",
                "artifact contains 'ok'",
                verify_command=(
                    f"py -c \"assert open({str(artifact)!r}).read().strip() == 'ok'\""
                ),
            ),
        ],
        scope=Scope(fair_game=[str(artifact)], hands_off=["goal_persistence/"]),
        stop_conditions=[StopCondition(kind="max_rounds", value=5)],
        how_to_work=["attempt work", "verify independently", "repeat until done"],
    )

    maker = ArtifactMaker(artifact)
    checker = ArtifactChecker(artifact)
    runtime = GoalRuntime(GoalStore(db))
    runner = GoalLoopRunner(
        spec,
        runtime,
        maker,
        checker,
        state_dir=state_dir,
        verifier=CommandVerifier(),
    )

    status = runner.run("demo-thread", budget_tokens=100_000)

    print("=" * 60)
    print(f"Final status: {status.value}")
    print(f"Loop state status: {runner._state.status}")
    print(f"Rounds: {runner._state.current_round}")
    print(f"Passed rounds: {runner._state.passed_rounds}")
    print(f"Failed rounds: {runner._state.failed_rounds}")
    print("=" * 60)

    assert status == GoalStatus.COMPLETE
    assert maker._calls >= 2, "demo did not exercise the fail-then-pass loop"
    print("Done.")


if __name__ == "__main__":
    main()
