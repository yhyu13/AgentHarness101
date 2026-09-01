"""Cluster C resilience tests: crash-safe in-flight turns, durable RunHistory ledger,
mid-turn budget enforcement, and poison-goal quarantine.

These exercise the durable goal_persistence layer directly (store + runtime) with a
throwaway SQLite DB, isolating the resilience affordances from the LLM boundary.
"""

from pathlib import Path
from datetime import datetime, timezone

import pytest

from goal_persistence import GoalRuntime, GoalStatus, GoalStore


@pytest.fixture
def runtime(tmp_path: Path) -> GoalRuntime:
    return GoalRuntime(GoalStore(tmp_path / "goals.db"))


def _future_iso(seconds: int) -> str:
    """An ISO timestamp ``seconds`` in the future (so it reads as not-yet-stale)."""
    return datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + seconds)


class TestInFlightMarker:
    """C1 + C18: a started turn leaves a durable marker; end_turn clears it."""

    def test_start_turn_writes_durable_marker(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective")
        runtime.start_turn("t1")
        assert runtime._store.list_in_flight() == ["t1"]

    def test_end_turn_clears_durable_marker(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective")
        runtime.start_turn("t1")
        runtime.end_turn("t1")
        assert runtime._store.list_in_flight() == []

    def test_reconcile_aborts_stale_in_flight_turn(self, runtime: GoalRuntime) -> None:
        # A crash leaves an orphaned marker with an old timestamp; on restart a fresh
        # runtime (empty _active_turns) must reconcile it as an aborted run.
        runtime.create_goal("t1", "objective")
        runtime.start_turn("t1")
        # Back-date the marker to simulate a crash well in the past.
        runtime._store.mark_in_flight("t1", datetime.fromtimestamp(1_000_000_000))
        fresh = GoalRuntime(runtime._store)
        aborted = fresh.reconcile_in_flight(abandon_after_s=3600)
        assert [a["thread_id"] for a in aborted] == ["t1"]
        assert aborted[0]["outcome"] == "aborted"
        # The dangling marker is gone and the goal is re-armable again.
        assert runtime._store.list_in_flight() == []

    def test_reconcile_leaves_fresh_in_flight_alone(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective")
        runtime.start_turn("t1")
        fresh_future = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + 120)
        runtime._store.mark_in_flight("t1", fresh_future)
        aborted = runtime.reconcile_in_flight(abandon_after_s=3600)
        assert aborted == []


class TestRunHistoryLedger:
    """C3: every terminal/abandoned outcome appends a durable, queryable ledger row."""

    def test_mark_complete_records_run(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective")
        runtime.mark_complete("t1", "evidence: exit 0")
        runs = runtime._store.list_runs(thread_id="t1")
        assert len(runs) == 1
        assert runs[0]["outcome"] == "completed"
        assert runs[0]["status"] == "complete"
        assert runs[0]["thread_id"] == "t1"

    def test_quarantine_records_run(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective")
        runtime.quarantine("t1", "repeated errors")
        runs = runtime._store.list_runs(thread_id="t1")
        assert len(runs) == 1
        assert runs[0]["outcome"] == "quarantined"

    def test_reconcile_records_aborted_run(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective")
        runtime.start_turn("t1")
        runtime._store.mark_in_flight("t1", datetime.fromtimestamp(1_000_000_000))
        fresh = GoalRuntime(runtime._store)
        fresh.reconcile_in_flight(abandon_after_s=3600)
        runs = runtime._store.list_runs(thread_id="t1")
        assert len(runs) == 1
        assert runs[0]["outcome"] == "aborted"

    def test_ledger_filters_by_thread(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("a", "objective a")
        runtime.create_goal("b", "objective b")
        runtime.mark_complete("a", "ev")
        runtime.mark_blocked("b", "no progress")  # must repeat to flip
        runtime.mark_blocked("b", "no progress")
        runtime.mark_blocked("b", "no progress")
        runs = runtime._store.list_runs(thread_id="b")
        assert len(runs) == 1
        assert runs[0]["outcome"] == "blocked"
        assert runtime._store.list_runs(thread_id="a")[0]["outcome"] == "completed"


class TestMidTurnBudget:
    """C5: budget is judged mid-turn (not only at end_turn flush)."""

    def test_budget_exceeded_reports_overshoot_before_end_turn(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective", budget_tokens=100)
        runtime.start_turn("t1")
        acc = runtime._active_turns["t1"]
        acc.add_llm_call(input_tokens=150, cached_input_tokens=0, output_tokens=0)
        # The durable row is still ACTIVE (nothing flushed yet), but the projected
        # usage already exceeds budget — the mid-turn check must catch it.
        assert runtime.get_goal("t1").is_active
        assert runtime.budget_exceeded("t1") == GoalStatus.BUDGET_LIMITED

    def test_budget_exceeded_none_within_budget(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective", budget_tokens=100)
        runtime.start_turn("t1")
        runtime._active_turns["t1"].add_llm_call(
            input_tokens=40, cached_input_tokens=0, output_tokens=20
        )
        assert runtime.budget_exceeded("t1") is None

    def test_budget_exceeded_no_active_turn(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective", budget_tokens=100)
        assert runtime.budget_exceeded("t1") is None


class TestQuarantine:
    """C4: poison goals are moved aside and excluded from resume, but re-armable."""

    def test_quarantine_moves_goal_out_of_active(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective")
        goal = runtime.quarantine("t1", "repeated runtime errors")
        assert goal.status == GoalStatus.QUARANTINED
        assert runtime.resume_all() == []  # excluded from re-arming

    def test_unquarantine_rearms_goal(self, runtime: GoalRuntime) -> None:
        runtime.create_goal("t1", "objective")
        runtime.quarantine("t1", "boom")
        goal = runtime.unquarantine("t1")
        assert goal.status == GoalStatus.ACTIVE
        assert [c.thread_id for c in runtime.resume_all()] == ["t1"]
