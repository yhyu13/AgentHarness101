"""Tests for the goal loop harness.

These tests drive the loop manually against an in-memory (echo/static) maker and
checker, with a real SQLite goal store and a real subprocess verifier. No LLM is
involved.
"""

from pathlib import Path

import pytest

from goal_loop import (
    AcceptanceCriterion,
    CommandVerifier,
    EchoMaker,
    GoalLoopRunner,
    GoalSpec,
    Issue,
    Severity,
    StaticChecker,
    StopCondition,
    Verdict,
)
from goal_persistence import GoalRuntime, GoalStatus, GoalStore
from sandbox import Sandbox
from observability import TraceLog
from hippocampus import Hippocampus, HippocampusStore
from tool_registry import Permission, ToolRegistry
from goal_loop.registered_roles import RegisteredChecker, RegisteredMaker


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "goals.db"


@pytest.fixture
def runtime(tmp_db: Path) -> GoalRuntime:
    return GoalRuntime(GoalStore(tmp_db))


def make_spec(
    *,
    max_rounds: int | None = None,
    criteria: list[AcceptanceCriterion] | None = None,
) -> GoalSpec:
    stop_conditions: list[StopCondition] = []
    if max_rounds is not None:
        stop_conditions.append(StopCondition(kind="max_rounds", value=max_rounds))
    return GoalSpec(
        objective="Implement a goal loop",
        acceptance_criteria=criteria or [AcceptanceCriterion(id="c1", description="criterion one")],
        stop_conditions=stop_conditions,
    )


class TestGoalSpec:
    def test_rejects_empty_objective(self) -> None:
        with pytest.raises(ValueError):
            GoalSpec(objective="   ", acceptance_criteria=[AcceptanceCriterion("c1", "d")])

    def test_rejects_zero_criteria(self) -> None:
        with pytest.raises(ValueError):
            GoalSpec(objective="o", acceptance_criteria=[])

    def test_parses_markdown(self) -> None:
        md = """# Goal
## Goal
Ship the thing.

## Acceptance Criteria
- [ ] tests pass @verify python -m pytest -q
- [ ] imports cleanly @verify python -c "import goal_loop"
- [ ] checker decides (no command)

## Scope
### Fair game
- goal_loop/
### Hands off
- goal_persistence/

## Stop Conditions
- Max turns reached: 5
- Budget exhausted

## How to Work
1. Read first.
2. Verify each step.
"""
        spec = GoalSpec.from_text(md)
        assert spec.objective == "Ship the thing."
        assert [c.id for c in spec.acceptance_criteria] == ["c1", "c2", "c3"]
        assert spec.acceptance_criteria[0].verify_command == "python -m pytest -q"
        assert spec.acceptance_criteria[2].verify_command is None
        assert spec.scope.fair_game == ["goal_loop/"]
        assert spec.scope.hands_off == ["goal_persistence/"]
        assert spec.stop_conditions[0].kind == "max_rounds"
        assert spec.stop_conditions[0].value == 5
        assert spec.how_to_work == ["Read first.", "Verify each step."]

    def test_rejects_missing_stop_conditions(self) -> None:
        md = """## Goal
Ship.
## Acceptance Criteria
- [ ] ok @verify python -c "pass"
## Scope
### Fair game
- x
"""
        with pytest.raises(ValueError):
            GoalSpec.from_text(md)

    def test_rejects_missing_acceptance(self) -> None:
        md = """## Goal
Ship.
## Stop Conditions
- Max turns reached: 5
"""
        with pytest.raises(ValueError):
            GoalSpec.from_text(md)

    def test_parses_bundled_template(self) -> None:
        from pathlib import Path

        template = Path(__file__).parent.parent / "src" / "goal_loop" / "templates" / "goal.md"
        spec = GoalSpec.from_markdown(template)
        assert spec.objective.startswith("Implement the XX feature")
        assert len(spec.acceptance_criteria) == 3
        assert all(c.verify_command for c in spec.acceptance_criteria)
        assert spec.stop_conditions[0].kind == "max_rounds"
        assert spec.stop_conditions[0].value == 20


class TestCommandVerifier:
    def test_pass(self) -> None:
        result = CommandVerifier().run("py -c \"print('ok')\"")
        assert result.ok
        assert result.returncode == 0

    def test_fail(self) -> None:
        result = CommandVerifier().run('py -c "raise SystemExit(3)"')
        assert not result.ok
        assert result.returncode == 3

    def test_timeout(self) -> None:
        result = CommandVerifier(timeout_s=1).run('py -c "import time; time.sleep(5)"')
        assert result.timed_out
        assert not result.ok

    def test_accepts_argv_list(self) -> None:
        result = CommandVerifier().run(["py", "-c", "print('ok')"])
        assert result.ok

    def test_argv_list_preserves_backslash_path(self) -> None:
        # A Windows-style path with backslashes must be forwarded verbatim as an argv
        # list (never re-split), so the path does not drift across platforms.
        argv = ["py", "-c", "print('ok')", r"C:\work\out.txt"]
        result = CommandVerifier().run(argv)
        assert result.ok
        assert result.command == r"py -c print('ok') C:\work\out.txt"


class TestLoopState:
    def test_records_round_stats(self) -> None:
        from goal_loop import LoopState, RoundRecord, Verdict
        from datetime import datetime, timezone

        state = LoopState(loop_name="o")
        state.record_round(
            RoundRecord(
                number=1,
                started_at=datetime.now(timezone.utc),
                checker_verdict=Verdict.FAIL,
                issues=[Issue(Severity.CRITICAL, "f:1", "bad", "evidence")],
            )
        )
        assert state.failed_rounds == 1
        assert state.total_issues == 1
        assert state.current_round == 1

    def test_round_trips_through_json(self) -> None:
        import json

        from goal_loop import FinalResult, LoopState, RoundRecord, Verdict
        from datetime import datetime, timezone

        state = LoopState(loop_name="o", status="complete")
        state.record_round(
            RoundRecord(
                number=1,
                started_at=datetime.now(timezone.utc),
                checker_verdict=Verdict.PASS,
                issues=[Issue(Severity.MINOR, "f:1", "minor", "evidence")],
            )
        )
        state.final_result = FinalResult(
            status="complete", summary="done", finished_at=datetime.now(timezone.utc)
        )

        restored = LoopState.from_dict(json.loads(json.dumps(state.to_dict())))
        assert restored.loop_name == "o"
        assert restored.status == "complete"
        assert restored.current_round == 1
        assert restored.rounds[0].checker_verdict == Verdict.PASS
        assert restored.rounds[0].issues[0].severity == Severity.MINOR
        assert restored.final_result.status == "complete"


class TestGoalLoopRunner:
    def test_completes_with_evidence(self, runtime: GoalRuntime, tmp_path: Path) -> None:
        spec = make_spec(
            criteria=[AcceptanceCriterion("c1", "pass", verify_command='py -c "pass"')]
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("implemented"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
        )
        status = runner.run("t1")
        assert status == GoalStatus.COMPLETE
        goal = runtime._store.get("t1")
        assert goal.status == GoalStatus.COMPLETE
        assert "verdict=pass" in goal.last_blocked_reason
        assert "c1" in goal.last_blocked_reason

    def test_stops_at_max_rounds_without_completing(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        spec = make_spec(
            max_rounds=2,
            criteria=[
                AcceptanceCriterion(
                    "c1", "never passes", verify_command='py -c "raise SystemExit(1)"'
                )
            ],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("implemented"),
            StaticChecker(Verdict.FAIL),
            state_dir=tmp_path,
        )
        status = runner.run("t1")
        assert status == GoalStatus.ACTIVE  # stopped, but not falsely completed
        goal = runtime._store.get("t1")
        assert goal.status == GoalStatus.ACTIVE
        assert runner._state.status == "stopped_max_rounds"

    def test_blocks_after_no_progress(self, runtime: GoalRuntime, tmp_path: Path) -> None:
        spec = make_spec(
            criteria=[
                AcceptanceCriterion("c1", "fails", verify_command='py -c "raise SystemExit(1)"')
            ],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("implemented"),
            StaticChecker(Verdict.FAIL),
            state_dir=tmp_path,
        )
        status = runner.run("t1")
        assert status == GoalStatus.BLOCKED

    def test_does_not_complete_on_maker_self_report_only(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # Criterion has no command, so only the checker can satisfy it. The checker
        # says FAIL, so the loop must not complete despite the maker's success claim.
        spec = make_spec(
            max_rounds=1,
            criteria=[AcceptanceCriterion("c1", "no command")],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("I finished everything myself"),
            StaticChecker(Verdict.FAIL),
            state_dir=tmp_path,
        )
        status = runner.run("t1")
        assert status == GoalStatus.ACTIVE
        assert runner._state.status == "stopped_max_rounds"

    def test_budget_auto_transition(self, tmp_db: Path, tmp_path: Path) -> None:
        runtime = GoalRuntime(GoalStore(tmp_db))
        spec = make_spec(
            criteria=[
                AcceptanceCriterion("c1", "fails", verify_command='py -c "raise SystemExit(1)"')
            ],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("implemented"),
            StaticChecker(Verdict.FAIL),
            state_dir=tmp_path,
        )
        status = runner.run("t1", budget_tokens=1)
        assert status == GoalStatus.BUDGET_LIMITED

    def test_resumes_from_persisted_state(self, tmp_db: Path, tmp_path: Path) -> None:
        runtime = GoalRuntime(GoalStore(tmp_db))
        spec = make_spec(
            max_rounds=2,
            # Command-less criterion: satisfaction is driven by the checker verdict, so
            # the first (FAIL) run makes no progress and the second (PASS) run completes.
            criteria=[AcceptanceCriterion("c1", "checker-decided")],
        )

        first = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("attempt 1"),
            StaticChecker(Verdict.FAIL),
            state_dir=tmp_path,
        )
        assert first.run("t1") == GoalStatus.ACTIVE  # stopped at max_rounds, still active

        # A fresh runner over the same store + state_dir must resume, not restart.
        second = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("attempt 2"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
        )
        status = second.run("t1")
        assert status == GoalStatus.COMPLETE
        # Round numbering continues from the prior run rather than resetting.
        assert second._state.current_round > 2

    def test_steering_prompt_is_passed_to_maker(self, runtime: GoalRuntime, tmp_path: Path) -> None:
        captured: dict = {}

        def capturing_maker(spec, state, steering):
            captured["steering"] = steering
            from goal_loop import MakerOutput

            return MakerOutput(summary="done", tokens_used=5)

        spec = make_spec(
            criteria=[AcceptanceCriterion("c1", "pass", verify_command='py -c "pass"')],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            capturing_maker,
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
        )
        runner.run("t1")
        assert "Implement a goal loop" in captured["steering"]
        assert "Keep the full objective intact" in captured["steering"]

    def test_budget_reflects_reported_usage(self, tmp_db: Path, tmp_path: Path) -> None:
        runtime = GoalRuntime(GoalStore(tmp_db))
        spec = make_spec(
            max_rounds=1,
            criteria=[
                AcceptanceCriterion("c1", "fails", verify_command='py -c "raise SystemExit(1)"')
            ],
        )
        maker = EchoMaker("implemented")
        runner = GoalLoopRunner(
            spec,
            runtime,
            maker,
            StaticChecker(Verdict.FAIL),
            state_dir=tmp_path,
        )
        runner.run("t1")
        goal = runtime.get_goal("t1")
        # EchoMaker reports len(steering)+len(summary); StaticChecker reports
        # len(summary). Neither is the magic 2 (1 input + 1 output) from before.
        assert goal.usage.tokens_input > 0
        assert goal.usage.tokens_output == 0

    def test_pass_with_failing_commands_blocks_after_three(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # A checker that keeps saying PASS while the command keeps failing must be
        # treated as no-progress and eventually BLOCKED, not allowed to spin forever.
        spec = make_spec(
            criteria=[
                AcceptanceCriterion("c1", "fails", verify_command='py -c "raise SystemExit(1)"')
            ],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("implemented"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
        )
        status = runner.run("t1")
        assert status == GoalStatus.BLOCKED
        assert runner._state.status == "blocked"

    def test_never_progressing_maker_bounds_blocked_path(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # A maker that never satisfies anything must hit BLOCKED after the
        # three-strike rule, not spin forever.
        class NeverProgress:
            def __call__(self, spec, state, steering):
                from goal_loop import MakerOutput

                return MakerOutput(summary="no progress", tokens_used=0)

        spec = make_spec(
            criteria=[
                AcceptanceCriterion("c1", "fails", verify_command='py -c "raise SystemExit(1)"')
            ],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            NeverProgress(),
            StaticChecker(Verdict.FAIL),
            state_dir=tmp_path,
        )
        status = runner.run("t1")
        assert status == GoalStatus.BLOCKED
        # The blocked path is bounded: it stops at the three-strike threshold.
        assert runtime.get_goal("t1").blocked_count >= 3

    def test_composes_sandbox_trace_and_hippocampus(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # The loop routes its verification command through a sandbox (allowlisted
        # python), logs maker/checker/verification events to a trace, and records the
        # round's trajectory into hippocampus.
        sandbox = Sandbox(allowlist=["python"])
        trace = TraceLog(tmp_path / "loop_trace.jsonl")
        hippo = Hippocampus(HippocampusStore(tmp_path / "memory"))

        spec = make_spec(
            criteria=[AcceptanceCriterion("c1", "pass", verify_command='python -c "pass"')],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("implemented"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
            sandbox=sandbox,
            trace_log=trace,
            hippocampus=hippo,
        )
        status = runner.run("t1")
        assert status == GoalStatus.COMPLETE

        # Trace captured the maker, checker, and verification events.
        events = trace.replay()
        assert any(e.event_type == "maker" for e in events)
        assert any(e.event_type == "checker" for e in events)
        assert any(e.event_type == "verification" for e in events)

        # Hippocampus recorded at least one trajectory for this thread.
        trajectories = list((tmp_path / "memory" / "trajectories").glob("*.json"))
        assert trajectories

    def test_wrong_artifact_content_does_not_complete(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # A maker that writes the wrong bytes must not pass an assert-based
        # verification command. This pins the demo's fix: content, not existence.
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from examples.goal_loop_demo import ArtifactChecker

        artifact = tmp_path / "wrong.txt"

        class WrongMaker:
            def __call__(self, spec, state, steering):
                from goal_loop import MakerOutput

                artifact.write_text("wrong\n", encoding="utf-8")
                return MakerOutput(summary="wrote wrong content", tokens_used=1)

        spec = make_spec(
            max_rounds=1,
            criteria=[
                AcceptanceCriterion(
                    "c1",
                    "artifact == 'ok'",
                    verify_command=(
                        f"py -c \"assert open({str(artifact)!r}).read().strip() == 'ok'\""
                    ),
                )
            ],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            WrongMaker(),
            ArtifactChecker(artifact),
            state_dir=tmp_path,
        )
        status = runner.run("t1")
        assert status != GoalStatus.COMPLETE

    def test_maker_checker_route_through_tool_registry(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        registry = ToolRegistry()

        def make_handler(objective: str):
            from goal_loop import MakerOutput

            return MakerOutput(summary=f"made {objective}", tokens_used=1)

        def check_handler(summary: str):
            from goal_loop import CheckerOutput, Verdict

            return CheckerOutput(verdict=Verdict.PASS, tokens_used=1)

        maker = RegisteredMaker(registry, "make", make_handler)
        checker = RegisteredChecker(registry, "check", check_handler)

        spec = make_spec(
            criteria=[AcceptanceCriterion("c1", "checker-decided")],
        )
        runner = GoalLoopRunner(spec, runtime, maker, checker, state_dir=tmp_path)
        status = runner.run("t1")
        assert status == GoalStatus.COMPLETE

    def test_maker_blocked_by_registry_does_not_complete(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        registry = ToolRegistry()

        def make_handler(objective: str):
            from goal_loop import MakerOutput

            return MakerOutput(summary="should not run", tokens_used=1)

        maker = RegisteredMaker(registry, "make", make_handler)
        # Disable the write permission: the maker tool is now blocked.
        registry.disable("make", Permission.WRITE)
        checker = StaticChecker(Verdict.PASS)

        spec = make_spec(
            max_rounds=1,
            criteria=[
                AcceptanceCriterion(
                    "c1", "must write file", verify_command='py -c "raise SystemExit(1)"'
                )
            ],
        )
        runner = GoalLoopRunner(spec, runtime, maker, checker, state_dir=tmp_path)
        status = runner.run("t1")
        assert status != GoalStatus.COMPLETE

    def test_run_until_terminal_continues_past_max_rounds(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # Event-driven, not timed: a run stopped at max_rounds while still ACTIVE must
        # be driven again immediately by run_until_terminal until completion.
        spec = make_spec(
            max_rounds=1,
            criteria=[AcceptanceCriterion("c1", "checker-decided")],
        )

        calls = {"n": 0}

        def fail_then_pass_checker(spec, maker_output):
            from goal_loop import CheckerOutput

            calls["n"] += 1
            verdict = Verdict.FAIL if calls["n"] == 1 else Verdict.PASS
            return CheckerOutput(verdict=verdict, tokens_used=1)

        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("attempt"),
            fail_then_pass_checker,
            state_dir=tmp_path,
        )
        status = runner.run_until_terminal("t1")
        assert status == GoalStatus.COMPLETE
        # Round numbering advanced across runs, proving continuation, not restart.
        assert runner.state.current_round >= 2

    def test_run_until_terminal_retries_transient_crash_in_place(
        self, runtime: GoalRuntime, tmp_path: Path, monkeypatch
    ) -> None:
        # A transient crash (e.g. connection reset) after some progress must be retried
        # on the SAME thread, resuming rather than restarting or losing progress.
        spec = make_spec(
            max_rounds=1,
            criteria=[AcceptanceCriterion("c1", "checker-decided")],
        )

        calls = {"n": 0}

        def fail_then_pass_checker(spec, maker_output):
            from goal_loop import CheckerOutput

            calls["n"] += 1
            verdict = Verdict.FAIL if calls["n"] == 1 else Verdict.PASS
            return CheckerOutput(verdict=verdict, tokens_used=1)

        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("attempt"),
            fail_then_pass_checker,
            state_dir=tmp_path,
        )

        real_run = runner.run
        run_calls = {"n": 0}

        def flaky_run(*args, **kwargs):
            run_calls["n"] += 1
            if run_calls["n"] == 2:
                raise ConnectionError("transient reset")
            return real_run(*args, **kwargs)

        monkeypatch.setattr(runner, "run", flaky_run)
        status = runner.run_until_terminal("t1")

        assert status == GoalStatus.COMPLETE
        assert run_calls["n"] == 3  # round 1 (FAIL), crash, resume -> complete
        assert runner.state.current_round == 2  # continued, not restarted

    def test_run_until_terminal_raises_after_persistent_crash(
        self, runtime: GoalRuntime, tmp_path: Path, monkeypatch
    ) -> None:
        # A persistent crash (>= max_crashes consecutive failures) must propagate,
        # not retry forever. This is the anti-spin bound on transient-failure recovery.
        spec = make_spec(
            criteria=[AcceptanceCriterion("c1", "checker-decided")],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("attempt"),
            StaticChecker(Verdict.PASS),
            state_dir=tmp_path,
        )

        def always_crash(*args, **kwargs):
            raise ConnectionError("persistent reset")

        monkeypatch.setattr(runner, "run", always_crash)
        with pytest.raises(ConnectionError):
            runner.run_until_terminal("t1", max_crashes=2)

    def test_run_until_terminal_stops_at_blocked(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # The other half of "run without stopping": when the goal hits the three-strike
        # BLOCKED terminal-ish state, run_until_terminal must return it and stop, not
        # keep driving a no-progress goal forever.
        spec = make_spec(
            criteria=[
                AcceptanceCriterion("c1", "fails", verify_command='py -c "raise SystemExit(1)"')
            ],
        )
        runner = GoalLoopRunner(
            spec,
            runtime,
            EchoMaker("attempt"),
            StaticChecker(Verdict.FAIL),
            state_dir=tmp_path,
        )
        status = runner.run_until_terminal("t1")
        assert status == GoalStatus.BLOCKED
        assert runtime.get_goal("t1").status == GoalStatus.BLOCKED
