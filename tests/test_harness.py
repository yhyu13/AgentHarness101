"""Harness tests for goal persistence.

These tests drive the lifecycle manually against a real SQLite DB and assert on
captured state-transition events. No LLM is involved.
"""

from pathlib import Path

import pytest

from goal_persistence import Goal, GoalRuntime, GoalStatus, GoalStore, TransitionError, Usage


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "goals.db"


@pytest.fixture
def store(tmp_db: Path) -> GoalStore:
    return GoalStore(tmp_db)


@pytest.fixture
def runtime(store: GoalStore) -> GoalRuntime:
    return GoalRuntime(store)


class TestStatusMachine:
    def test_active_can_transition_to_all_non_terminal(self, store: GoalStore) -> None:
        goal = store.create(Goal(thread_id="t1", objective="o"))
        for status in (
            GoalStatus.PAUSED,
            GoalStatus.BLOCKED,
            GoalStatus.USAGE_LIMITED,
            GoalStatus.BUDGET_LIMITED,
            GoalStatus.COMPLETE,
        ):
            store.create(Goal(thread_id=f"t-{status.value}", objective="o"))
            g = store.transition(f"t-{status.value}", status)
            assert g.status == status

    def test_terminal_states_are_terminal(self, store: GoalStore) -> None:
        store.create(Goal(thread_id="t1", objective="o"))
        store.transition("t1", GoalStatus.COMPLETE)
        with pytest.raises(TransitionError):
            store.transition("t1", GoalStatus.ACTIVE)

    def test_invalid_transition_rejected(self, store: GoalStore) -> None:
        store.create(Goal(thread_id="t1", objective="o", status=GoalStatus.COMPLETE))
        with pytest.raises(TransitionError):
            store.transition("t1", GoalStatus.PAUSED)


class TestPersistence:
    def test_goal_survives_store_reopen(self, tmp_db: Path) -> None:
        store1 = GoalStore(tmp_db)
        store1.create(Goal(thread_id="t1", objective="Build a harness"))

        store2 = GoalStore(tmp_db)
        goal = store2.get("t1")
        assert goal is not None
        assert goal.objective == "Build a harness"
        assert goal.status == GoalStatus.ACTIVE

    def test_usage_is_persisted(self, store: GoalStore) -> None:
        store.create(Goal(thread_id="t1", objective="o"))
        store.apply_usage("t1", Usage(tokens_input=100, tokens_output=50, wall_ms=10))
        goal = store.get("t1")
        assert goal.usage.tokens == 150
        assert goal.usage.wall_ms == 10


class TestAccounting:
    def test_token_delta_formula(self) -> None:
        u = Usage(tokens_input=1000, tokens_cached_input=800, tokens_output=200)
        assert u.tokens == (1000 - 800) + 200

    def test_turn_accounting_tracks_usage(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        acc = runtime.start_turn("t1")
        acc.add_llm_call(input_tokens=100, cached_input_tokens=20, output_tokens=30)
        goal = runtime.end_turn("t1")
        assert goal.usage.tokens == (100 - 20) + 30
        assert goal.usage.wall_ms >= 0

    def test_budget_auto_transition(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o", budget_tokens=50)
        acc = runtime.start_turn("t1")
        acc.add_llm_call(input_tokens=30, cached_input_tokens=0, output_tokens=30)
        goal = runtime.end_turn("t1")
        assert goal.status == GoalStatus.BUDGET_LIMITED
        assert goal.usage.tokens == 60

    def test_time_budget_auto_transition(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o", budget_wall_ms=1)
        acc = runtime.start_turn("t1")
        # Force some wall time to elapse.
        import time

        time.sleep(0.005)
        goal = runtime.end_turn("t1")
        assert goal.status == GoalStatus.BUDGET_LIMITED


class TestIdleSelfStart:
    def test_continuation_when_idle_and_active(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "Implement goal persistence")
        cont = runtime.maybe_continue("t1")
        assert cont is not None
        assert cont.thread_id == "t1"
        assert "Implement goal persistence" in cont.steering_prompt
        assert "Keep the full objective intact" in cont.steering_prompt

    def test_no_continuation_when_turn_in_flight(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        runtime.start_turn("t1")
        assert runtime.maybe_continue("t1") is None

    def test_no_continuation_for_terminal_goal(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        runtime.start_turn("t1")
        runtime.end_turn("t1", status_override=GoalStatus.COMPLETE)
        assert runtime.maybe_continue("t1") is None

    def test_exactly_one_continuation_per_idle(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        first = runtime.maybe_continue("t1")
        second = runtime.maybe_continue("t1")
        assert first is not None
        # Second call on the same idle moment returns the same continuation,
        # not a new queued turn.
        assert second is not None
        assert first.thread_id == second.thread_id


class TestResume:
    def test_resume_re_arms_idle_loop(self, tmp_db: Path) -> None:
        runtime1 = GoalRuntime(GoalStore(tmp_db))
        runtime1.create_goal("t1", "o")

        runtime2 = GoalRuntime(GoalStore(tmp_db))
        cont = runtime2.resume("t1")
        assert cont is not None
        assert cont.goal.status == GoalStatus.ACTIVE

    def test_resume_all_active_goals(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        runtime.create_goal("t2", "o")
        runtime.create_goal("t3", "o")
        runtime.start_turn("t3")
        runtime.end_turn("t3", status_override=GoalStatus.COMPLETE)

        conts = runtime.resume_all()
        assert {c.thread_id for c in conts} == {"t1", "t2"}


class TestBlockedAudit:
    def test_blocked_requires_three_consecutive_turns(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        g1 = runtime.mark_blocked("t1", "network down")
        assert g1.status == GoalStatus.ACTIVE  # not enough yet
        assert g1.blocked_count == 1

        g2 = runtime.mark_blocked("t1", "network down")
        assert g2.status == GoalStatus.ACTIVE
        assert g2.blocked_count == 2

        g3 = runtime.mark_blocked("t1", "network down")
        assert g3.status == GoalStatus.BLOCKED
        assert g3.blocked_count == 3

    def test_unblocking_resets_counter(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        runtime.mark_blocked("t1", "network down")
        runtime.mark_blocked("t1", "network down")
        runtime.unblock("t1")
        g = runtime.mark_blocked("t1", "network down")
        assert g.status == GoalStatus.ACTIVE
        assert g.blocked_count == 1


class TestCompletionAudit:
    def test_complete_requires_evidence(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o")
        goal = runtime.mark_complete("t1", "tests passed")
        assert goal.status == GoalStatus.COMPLETE
        assert goal.last_blocked_reason == "tests passed"


class TestLifecycleEvents:
    def test_full_manual_lifecycle(self, runtime: GoalRuntime) -> None:
        # 1. Create an active goal.
        runtime.create_goal(
            "t1", "Build a goal persistence harness", budget_tokens=1000
        )

        # 2. Idle self-start produces a continuation steering prompt.
        cont = runtime.maybe_continue("t1")
        assert cont is not None
        assert cont.goal.status == GoalStatus.ACTIVE

        # 3. Start a turn, run a tool, record usage, end the turn.
        acc = runtime.start_turn("t1")
        runtime.notify_tool_finish("t1")
        acc.add_llm_call(input_tokens=100, cached_input_tokens=10, output_tokens=40)
        goal = runtime.end_turn("t1")
        assert goal.status == GoalStatus.ACTIVE
        assert goal.usage.tokens == 130

        # 4. Next idle moment also produces a continuation.
        cont2 = runtime.maybe_continue("t1")
        assert cont2 is not None
        assert "130" in cont2.steering_prompt

        # 5. A tool error is recorded; turn continues.
        acc2 = runtime.start_turn("t1")
        runtime.notify_tool_error("t1", "rate limit")
        acc2.add_llm_call(input_tokens=50, cached_input_tokens=0, output_tokens=20)
        goal2 = runtime.end_turn("t1")
        assert goal2.status == GoalStatus.ACTIVE

        # 6. Simulate a blocking condition observed once.
        runtime.mark_blocked("t1", "missing api key")
        goal3 = runtime.maybe_continue("t1").goal  # still active
        assert goal3.status == GoalStatus.ACTIVE

        # 7. After three consecutive blocked observations, status flips.
        runtime.mark_blocked("t1", "missing api key")
        runtime.mark_blocked("t1", "missing api key")
        blocked = runtime._store.get("t1")
        assert blocked.status == GoalStatus.BLOCKED

        # 8. Human unblocks; work resumes.
        runtime.unblock("t1")
        assert runtime.maybe_continue("t1") is not None

        # 9. Work completes with evidence.
        final = runtime.mark_complete("t1", "harness tests pass")
        assert final.status == GoalStatus.COMPLETE
        assert runtime.maybe_continue("t1") is None

    def test_budget_limited_escape_hatch(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "o", budget_tokens=10)
        acc = runtime.start_turn("t1")
        acc.add_llm_call(input_tokens=20, cached_input_tokens=0, output_tokens=0)
        goal = runtime.end_turn("t1")
        assert goal.status == GoalStatus.BUDGET_LIMITED
        assert runtime.maybe_continue("t1") is None
