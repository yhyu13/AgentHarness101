"""World verifier tests: re-read artifacts and assert content, never trust self-report.

These tests pin the "verify the world, not the self-report" seam (deepseek
``testing.md:27-29`` + learn-harness verification subsystem): a fake exit-0 command and
a lying checker must not complete a goal when the artifact on disk is wrong or missing.
"""

from pathlib import Path

import pytest

from goal_loop import (
    AcceptanceCriterion,
    CheckerOutput,
    EchoMaker,
    GoalLoopRunner,
    GoalSpec,
    MakerOutput,
    StaticChecker,
    StopCondition,
    Verdict,
)
from goal_loop.world_verifier import WorldCheck, WorldVerifier
from goal_persistence import GoalRuntime, GoalStatus, GoalStore


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "goals.db"


@pytest.fixture
def runtime(tmp_db: Path) -> GoalRuntime:
    return GoalRuntime(GoalStore(tmp_db))


class _LyingChecker:
    """Always PASS, regardless of machine or world evidence."""

    def __call__(self, spec, output):
        return CheckerOutput(verdict=Verdict.PASS, tokens_used=0)


def _spec() -> GoalSpec:
    """One criterion with a fake exit-0 verify command (``py -c "pass"``), which is the
    Windows equivalent of ``true`` / ``echo 0``: it exits 0 without inspecting anything."""
    return GoalSpec(
        objective="write the right artifact",
        acceptance_criteria=[
            AcceptanceCriterion("c1", "artifact matches", verify_command='py -c "pass"')
        ],
        stop_conditions=[StopCondition(kind="max_rounds", value=10)],
    )


class TestWorldVerifier:
    def test_verify_unchanged_file_is_byte_identical(self, tmp_path: Path) -> None:
        """deepseek testing.md:29 — assert untouched files are byte-identical."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_bytes(b"hello world\n")
        result = WorldVerifier().verify(artifact, expected="hello world\n")
        assert result.ok
        assert result.observed == "hello world\n"
        assert result.expected == "hello world\n"

    def test_verify_keyword_hit(self, tmp_path: Path) -> None:
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("prefix TARGET suffix", encoding="utf-8")
        result = WorldVerifier().verify(artifact, contains="TARGET")
        assert result.ok

    def test_verify_keyword_miss_reports_observed_vs_expected(
        self, tmp_path: Path
    ) -> None:
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("wrong content", encoding="utf-8")
        result = WorldVerifier().verify(artifact, contains="TARGET")
        assert not result.ok
        assert result.observed == "wrong content"
        assert "TARGET" in result.expected

    def test_failure_message_includes_fix_guidance(self, tmp_path: Path) -> None:
        """learn-harness lecture-10:103-111 — errors carry what / why / fix."""
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("wrong", encoding="utf-8")
        result = WorldVerifier().verify(artifact, expected="ok")
        assert not result.ok
        assert result.what
        assert result.why
        assert result.fix
        assert str(artifact) in result.fix
        assert "ok" in result.fix

    def test_world_check_requires_exactly_one_assertion(self) -> None:
        with pytest.raises(ValueError):
            WorldCheck("artifact.txt")
        with pytest.raises(ValueError):
            WorldCheck("artifact.txt", expected="a", contains="b")


class TestWorldVerifierInLoop:
    def test_wrong_artifact_with_fake_exit_0_does_not_complete(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        """The hole Era 23 missed: exit 0 + lying checker + wrong artifact on disk."""
        artifact = tmp_path / "artifact.txt"

        class WrongMaker:
            def __call__(self, spec, state, steering):
                artifact.write_text("wrong\n", encoding="utf-8")
                return MakerOutput(
                    summary="wrote wrong content",
                    modified_files=[str(artifact)],
                    tokens_used=1,
                )

        runner = GoalLoopRunner(
            _spec(),
            runtime,
            WrongMaker(),
            _LyingChecker(),
            state_dir=tmp_path,
            world_verifier=WorldVerifier([WorldCheck(artifact, expected="ok")]),
        )
        status = runner.run("t1")
        assert status != GoalStatus.COMPLETE
        assert status == GoalStatus.BLOCKED

    def test_missing_artifact_with_fake_exit_0_does_not_complete(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        artifact = tmp_path / "artifact.txt"  # never written

        class NoOpMaker:
            def __call__(self, spec, state, steering):
                return MakerOutput(summary="did nothing", tokens_used=1)

        runner = GoalLoopRunner(
            _spec(),
            runtime,
            NoOpMaker(),
            _LyingChecker(),
            state_dir=tmp_path,
            world_verifier=WorldVerifier([WorldCheck(artifact, expected="ok")]),
        )
        status = runner.run("t1")
        assert status != GoalStatus.COMPLETE
        assert status == GoalStatus.BLOCKED

    def test_correct_artifact_with_exit_0_completes(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        artifact = tmp_path / "artifact.txt"

        class CorrectMaker:
            def __call__(self, spec, state, steering):
                artifact.write_text("ok", encoding="utf-8")
                return MakerOutput(
                    summary="wrote ok",
                    modified_files=[str(artifact)],
                    tokens_used=1,
                )

        runner = GoalLoopRunner(
            _spec(),
            runtime,
            CorrectMaker(),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
            world_verifier=WorldVerifier([WorldCheck(artifact, expected="ok")]),
        )
        status = runner.run("t1")
        assert status == GoalStatus.COMPLETE

    def test_without_world_verifier_is_backward_compatible(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        """No world_verifier arg keeps the old behavior: exit-0 command completes."""
        runner = GoalLoopRunner(
            _spec(),
            runtime,
            EchoMaker("done"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
        )
        status = runner.run("t1")
        assert status == GoalStatus.COMPLETE
