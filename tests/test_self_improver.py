"""Self-improvement loop tests: distill a run's outcome into a durable lesson, then
re-inject relevant lessons on the next run.

These pin the "越跑越好 = 记忆闭环" seam (§5 of the harness-skills survey:
claude-mem `capture→compress→reinject`, self-rag self-reflection, Acontext
"skills as memory"). The hippocampus already records; this closes the loop — outcome
→ lesson → steering — deterministically, with the LLM boundary left untouched.
"""

from pathlib import Path

import pytest

from goal_loop import (
    AcceptanceCriterion,
    EchoMaker,
    GoalLoopRunner,
    GoalSpec,
    MakerOutput,
    StaticChecker,
    StopCondition,
    Verdict,
)
from goal_loop.self_improver import SelfImprover
from goal_persistence import GoalRuntime, GoalStatus, GoalStore
from hippocampus import Hippocampus, HippocampusStore


@pytest.fixture
def hippocampus(tmp_path: Path) -> Hippocampus:
    return Hippocampus(HippocampusStore(tmp_path / "memory"))


@pytest.fixture
def runtime(tmp_path: Path) -> GoalRuntime:
    return GoalRuntime(GoalStore(tmp_path / "goals.db"))


def _objective() -> str:
    return "write a fibonacci function"


class _RecordingMaker:
    """A maker that captures the steering prompt it was handed each round."""

    def __init__(self, summary: str = "done") -> None:
        self._summary = summary
        self.steering: list[str] = []

    def __call__(self, spec, state, steering):
        self.steering.append(steering)
        return MakerOutput(summary=self._summary, tokens_used=1)


class TestSelfImprover:
    def test_distill_complete_marks_repeatable(self, hippocampus: Hippocampus) -> None:
        fact = SelfImprover(hippocampus).distill(
            "t1", _objective(), "complete", "all criteria verified", issues=[]
        )
        assert fact.correct is True
        assert "[repeat]" in fact.value
        assert _objective() in fact.value

    def test_distill_blocked_marks_avoid(self, hippocampus: Hippocampus) -> None:
        fact = SelfImprover(hippocampus).distill(
            "t1", _objective(), "blocked", "no progress", issues=["command failed"]
        )
        assert fact.correct is False
        assert "[avoid]" in fact.value
        assert "command failed" in fact.value

    def test_relevant_lessons_matches_overlapping_objective(
        self, hippocampus: Hippocampus
    ) -> None:
        improver = SelfImprover(hippocampus)
        improver.distill("t1", _objective(), "complete", "iterative worked")
        matches = improver.relevant_lessons(_objective())
        assert any("[repeat]" in m.value for m in matches)

    def test_relevant_lessons_ignores_unrelated_objective(
        self, hippocampus: Hippocampus
    ) -> None:
        improver = SelfImprover(hippocampus)
        improver.distill("t1", _objective(), "complete", "iterative worked")
        assert improver.relevant_lessons("build a web server with sockets") == []

    def test_relevant_lessons_empty_objective_matches_nothing(
        self, hippocampus: Hippocampus
    ) -> None:
        improver = SelfImprover(hippocampus)
        improver.distill("t1", _objective(), "complete", "done")
        assert improver.relevant_lessons("") == []
        assert improver.relevant_lessons("a b") == []  # no content words (len >= 3)

    def test_steering_context_empty_without_lessons(
        self, hippocampus: Hippocampus
    ) -> None:
        assert SelfImprover(hippocampus).steering_context(_objective()) == ""

    def test_steering_context_renders_prior_lessons(
        self, hippocampus: Hippocampus
    ) -> None:
        improver = SelfImprover(hippocampus)
        improver.distill("t1", _objective(), "blocked", "no progress", ["crashed"])
        ctx = improver.steering_context(_objective())
        assert "Prior lessons" in ctx
        assert "[avoid]" in ctx

    def test_distill_is_persisted_and_readable(self, hippocampus: Hippocampus) -> None:
        SelfImprover(hippocampus).distill("t1", _objective(), "complete", "done")
        assert hippocampus.get("self-improve::t1") is not None


class TestHippocampusFacts:
    def test_facts_lists_correct_and_incorrect(self, hippocampus: Hippocampus) -> None:
        hippocampus.learn("a", "good", correct=True)
        hippocampus.learn("b", "bad", correct=False)
        facts = hippocampus.facts()
        keys = {f.key for f in facts}
        assert {"a", "b"} <= keys


class TestSelfImproverInLoop:
    def _completing_spec(self) -> GoalSpec:
        return GoalSpec(
            objective=_objective(),
            acceptance_criteria=[
                AcceptanceCriterion("c1", "it works", verify_command='py -c "pass"')
            ],
            stop_conditions=[StopCondition(kind="max_rounds", value=10)],
        )

    def _blocking_spec(self) -> GoalSpec:
        return GoalSpec(
            objective=_objective(),
            acceptance_criteria=[
                AcceptanceCriterion("c1", "it works", verify_command='py -c "exit(1)"')
            ],
            stop_conditions=[StopCondition(kind="max_rounds", value=10)],
        )

    def test_complete_run_distills_repeat_lesson(
        self, runtime: GoalRuntime, hippocampus: Hippocampus, tmp_path: Path
    ) -> None:
        runner = GoalLoopRunner(
            self._completing_spec(),
            runtime,
            EchoMaker("done"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
            self_improver=SelfImprover(hippocampus),
        )
        assert runner.run("t1") == GoalStatus.COMPLETE
        fact = hippocampus.get("self-improve::t1")
        assert fact is not None
        assert fact.correct is True

    def test_blocked_run_distills_avoid_lesson(
        self, runtime: GoalRuntime, hippocampus: Hippocampus, tmp_path: Path
    ) -> None:
        runner = GoalLoopRunner(
            self._blocking_spec(),
            runtime,
            EchoMaker("tried"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
            self_improver=SelfImprover(hippocampus),
        )
        assert runner.run("t1") == GoalStatus.BLOCKED
        fact = hippocampus.get("self-improve::t1")
        assert fact is not None
        assert fact.correct is False

    def test_second_run_injects_prior_lesson_into_steering(
        self, runtime: GoalRuntime, hippocampus: Hippocampus, tmp_path: Path
    ) -> None:
        # A prior blocked run on the same objective leaves an "avoid" lesson behind.
        first = GoalLoopRunner(
            self._blocking_spec(),
            runtime,
            EchoMaker("tried"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path / "first",
            self_improver=SelfImprover(hippocampus),
        )
        assert first.run("t0") == GoalStatus.BLOCKED

        # A fresh run on the same objective must re-inject that lesson into steering.
        recorder = _RecordingMaker()
        second = GoalLoopRunner(
            self._completing_spec(),
            runtime,
            recorder,
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path / "second",
            self_improver=SelfImprover(hippocampus),
        )
        second.run("t2")
        assert any("Prior lessons" in s for s in recorder.steering)
        assert any("[avoid]" in s for s in recorder.steering)

    def test_without_self_improver_is_backward_compatible(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        runner = GoalLoopRunner(
            self._completing_spec(),
            runtime,
            EchoMaker("done"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
        )
        assert runner.run("t1") == GoalStatus.COMPLETE
