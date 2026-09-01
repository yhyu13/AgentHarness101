"""Guard-branch tests: exercise the fail-closed / error paths the happy-path tests skip.

Every branch here is real defensive code (a KeyError/RuntimeError guard, a timeout, a
permission denial) that would otherwise sit uncovered. No LLM is involved; these tests
pin that each guard raises or rejects exactly as documented.
"""

from pathlib import Path

import pytest

from goal_loop import CheckerOutput, CommandVerifier, MakerOutput, Verdict
from goal_loop.registered_roles import RegisteredChecker
from goal_persistence import Goal, GoalRuntime, GoalStatus, GoalStore, TransitionError, Usage
from safety import Approval, Decision, SafetyGuard
from sandbox import Sandbox
from tool_registry import Permission, ToolRegistry, ToolSpec


# ------------------------------------------------------------------ runtime guards


@pytest.fixture
def runtime(tmp_path: Path) -> GoalRuntime:
    return GoalRuntime(GoalStore(tmp_path / "goals.db"))


class TestRuntimeGuards:
    def test_start_turn_unknown_goal_raises(self, runtime: GoalRuntime) -> None:
        with pytest.raises(KeyError):
            runtime.start_turn("nope")

    def test_start_turn_in_flight_raises(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        runtime.start_turn("t1")
        with pytest.raises(RuntimeError):
            runtime.start_turn("t1")

    def test_start_turn_non_active_raises(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        runtime.start_turn("t1")
        runtime.end_turn("t1", status_override=GoalStatus.COMPLETE)
        with pytest.raises(RuntimeError):
            runtime.start_turn("t1")

    def test_end_turn_without_active_raises(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        with pytest.raises(RuntimeError):
            runtime.end_turn("t1")

    def test_notify_tool_finish_without_turn_raises(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        with pytest.raises(RuntimeError):
            runtime.notify_tool_finish("t1")

    def test_notify_tool_error_without_turn_raises(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        with pytest.raises(RuntimeError):
            runtime.notify_tool_error("t1", "boom")

    def test_resume_all_skips_in_flight_goal(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        runtime.create_goal("t2", "o")
        runtime.start_turn("t1")  # in-flight, must be excluded from resume
        assert [c.thread_id for c in runtime.resume_all()] == ["t2"]

    def test_mark_complete_unknown_goal_raises(self, runtime: GoalRuntime) -> None:
        with pytest.raises(KeyError):
            runtime.mark_complete("nope", "evidence")

    def test_mark_blocked_unknown_goal_raises(self, runtime: GoalRuntime) -> None:
        with pytest.raises(KeyError):
            runtime.mark_blocked("nope", "reason")

    def test_unblock_unknown_goal_raises(self, runtime: GoalRuntime) -> None:
        with pytest.raises(KeyError):
            runtime.unblock("nope")


# ------------------------------------------------------------------ store guards


class TestStoreGuards:
    def test_transition_unknown_goal_raises(self, tmp_path: Path) -> None:
        with pytest.raises(KeyError):
            GoalStore(tmp_path / "g.db").transition("nope", GoalStatus.PAUSED)

    def test_apply_usage_unknown_goal_raises(self, tmp_path: Path) -> None:
        with pytest.raises(KeyError):
            GoalStore(tmp_path / "g.db").apply_usage("nope", Usage())

    def test_save_upserts_missing_goal(self, tmp_path: Path) -> None:
        store = GoalStore(tmp_path / "g.db")
        store.save(Goal(thread_id="t1", objective="o"))  # no existing row -> create
        assert store.get("t1") is not None

    def test_delete_returns_bool(self, tmp_path: Path) -> None:
        store = GoalStore(tmp_path / "g.db")
        store.create(Goal(thread_id="t1", objective="o"))
        assert store.delete("t1") is True
        assert store.delete("t1") is False


# ------------------------------------------------------------------ registry guards


class TestRegistryGuards:
    def test_duplicate_register_raises(self) -> None:
        reg = ToolRegistry()
        spec = ToolSpec(name="t", description="d", permission=Permission.READ)
        reg.register(spec, lambda: None)
        with pytest.raises(ValueError):
            reg.register(spec, lambda: None)

    def test_unknown_tool_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.call("nope", {})
        with pytest.raises(KeyError):
            reg.enable("nope", Permission.READ)

    def test_disable_without_enable_is_noop(self) -> None:
        reg = ToolRegistry()
        reg.register(ToolSpec(name="t", description="d", permission=Permission.READ), lambda: None)
        reg.disable("t", Permission.READ)  # nothing enabled yet; must not raise

    def test_integer_schema_type_mismatch(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolSpec(
                name="t",
                description="d",
                permission=Permission.READ,
                parameters_schema={"type": "object", "properties": {"n": {"type": "integer"}}},
            ),
            lambda n: n,
        )
        reg.enable("t", Permission.READ)
        result = reg.call("t", {"n": "not-an-int"})
        assert not result.ok
        assert "must be an integer" in result.error

    def test_string_schema_type_mismatch(self) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolSpec(
                name="t",
                description="d",
                permission=Permission.READ,
                parameters_schema={"type": "object", "properties": {"s": {"type": "string"}}},
            ),
            lambda s: s,
        )
        reg.enable("t", Permission.READ)
        result = reg.call("t", {"s": 123})
        assert not result.ok
        assert "must be a string" in result.error


# ------------------------------------------------------------------ sandbox / verifier


class TestSandboxGuards:
    def test_empty_command_blocked(self) -> None:
        sb = Sandbox(allowlist=["py"])
        result = sb.run([])
        assert result.blocked
        assert result.reason == "empty command"

    def test_timeout_is_reported(self) -> None:
        sb = Sandbox(allowlist=["py"], timeout_s=0.1)
        result = sb.run(["py", "-c", "import time; time.sleep(5)"])
        assert result.timed_out

    def test_missing_executable_reports_oserror(self) -> None:
        sb = Sandbox(allowlist=["definitely-not-a-real-cmd-xyz"])
        result = sb.run(["definitely-not-a-real-cmd-xyz"])
        assert not result.ok
        assert result.returncode == 127


class TestVerifierGuards:
    def test_missing_executable_returns_127(self) -> None:
        result = CommandVerifier().run(["definitely-not-a-real-cmd-xyz"])
        assert result.returncode == 127
        assert "failed to run command" in result.stderr


# ------------------------------------------------------------------ safety / models / registered roles


class TestSafetyGuards:
    def test_normal_read_returns_approved(self) -> None:
        assert SafetyGuard().request("read", "t").approval == Approval.APPROVED

    def test_approve_non_pending_is_identity(self) -> None:
        decision = Decision(Approval.APPROVED)
        assert SafetyGuard().approve(decision) == decision


class TestModelGuards:
    def test_usage_limited_is_not_terminal(self) -> None:
        assert GoalStatus.USAGE_LIMITED.is_terminal is False

    def test_with_status_noop_self_transition_keeps_reason(self) -> None:
        goal = Goal(thread_id="t", objective="o", status=GoalStatus.BLOCKED, blocked_count=3)
        goal.with_status(GoalStatus.BLOCKED, reason="still blocked")
        assert goal.blocked_count == 3  # no-op transition must not double-count

    def test_invalid_transition_raises(self) -> None:
        goal = Goal(thread_id="t", objective="o", status=GoalStatus.COMPLETE)
        with pytest.raises(TransitionError):
            goal.with_status(GoalStatus.ACTIVE)


class TestRegisteredRoles:
    def test_registered_checker_blocked_tool_fails_closed(self) -> None:
        reg = ToolRegistry()

        def checker_tool(summary):
            return CheckerOutput(verdict=Verdict.PASS)

        checker = RegisteredChecker(reg, "check", checker_tool)
        # Revoke the READ permission the constructor granted; the call is then blocked
        # and RegisteredChecker must translate a blocked call into a FAIL verdict.
        reg.disable("check", Permission.READ)
        out = checker(None, MakerOutput(summary="x"))
        assert out.verdict == Verdict.FAIL
