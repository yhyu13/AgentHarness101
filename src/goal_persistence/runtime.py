from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from goal_persistence.accounting import TurnAccounting
from goal_persistence.models import Goal, GoalStatus
from goal_persistence.store import GoalStore


ANTI_DRIFT_TEMPLATE = """\
You are continuing an existing goal. Do not narrow or redefine success.

OBJECTIVE:
{objective}

CONTRACT:
- Keep the full objective intact. Do not redefine success around a smaller or easier task.
- Completion audit: verify against actual state with evidence before marking complete; never on your own say-so.
- Blocked audit: mark blocked only after the same blocking condition recurred for at least three consecutive goal turns.

Current status: {status}
Cumulative usage: {usage} tokens, {wall_ms} ms wall-clock.
"""


@dataclass(frozen=True)
class Continuation:
    """A request to start a fresh continuation turn for an active goal."""

    thread_id: str
    steering_prompt: str
    goal: Goal


@dataclass
class TurnResult:
    """Result of a simulated turn for test harnesses."""

    thread_id: str
    goal: Goal
    accounting: TurnAccounting
    events: list[str] = field(default_factory=list)


class GoalRuntime:
    """Idle self-start + resume runtime for persistent goals.

    The runtime is deliberately model-agnostic: it drives the lifecycle and
    produces continuation steering prompts, but does not itself invoke an LLM.
    """

    BLOCKED_THRESHOLD = 3

    def __init__(self, store: GoalStore) -> None:
        self._store = store
        self._active_turns: dict[str, TurnAccounting] = {}
        self._idle_hooks: list[Callable[[Continuation], Optional[str]]] = []

    # ------------------------------------------------------------------ lifecycle

    def create_goal(
        self,
        thread_id: str,
        objective: str,
        budget_tokens: Optional[int] = None,
        budget_wall_ms: Optional[int] = None,
    ) -> Goal:
        goal = Goal(
            thread_id=thread_id,
            objective=objective,
            budget_tokens=budget_tokens,
            budget_wall_ms=budget_wall_ms,
        )
        return self._store.create(goal)

    def get_goal(self, thread_id: str) -> Optional[Goal]:
        """Read the durable goal row for a thread, if one exists."""
        return self._store.get(thread_id)

    def start_turn(self, thread_id: str) -> TurnAccounting:
        """Begin tracking a new turn in memory.

        Raises if another turn is already in flight for this thread.
        """
        if thread_id in self._active_turns:
            raise RuntimeError(f"Turn already in flight for thread {thread_id}")
        goal = self._store.get(thread_id)
        if goal is None:
            raise KeyError(f"Goal not found for thread {thread_id}")
        if not goal.is_active:
            raise RuntimeError(f"Goal {thread_id} is not active ({goal.status.value})")
        acc = TurnAccounting()
        self._active_turns[thread_id] = acc
        return acc

    def end_turn(self, thread_id: str, status_override: Optional[GoalStatus] = None) -> Goal:
        """Flush in-memory accounting to the durable row.

        Optionally transition status (e.g. to paused / complete). Budget
        auto-transition happens inside apply_usage.
        """
        acc = self._active_turns.pop(thread_id, None)
        if acc is None:
            raise RuntimeError(f"No active turn for thread {thread_id}")
        goal = self._store.apply_usage(thread_id, acc.to_usage())
        if status_override is not None:
            goal = self._store.transition(thread_id, status_override)
        return goal

    def notify_tool_finish(self, thread_id: str) -> None:
        """Record that a tool finished during the current turn."""
        if thread_id not in self._active_turns:
            raise RuntimeError(f"No active turn for thread {thread_id}")

    def notify_tool_error(self, thread_id: str, error: str) -> None:
        """Record a tool error during the current turn.

        The turn itself continues; the harness decides whether to stop.
        """
        if thread_id not in self._active_turns:
            raise RuntimeError(f"No active turn for thread {thread_id}")

    # ------------------------------------------------------------------ idle / resume

    def maybe_continue(self, thread_id: str) -> Optional[Continuation]:
        """Idle self-start.

        If the thread is genuinely idle (no turn in flight) and the goal is
        still active, return a Continuation. Otherwise return None — no
        queueing, exactly one continuation per idle moment.
        """
        if thread_id in self._active_turns:
            return None  # genuinely busy
        goal = self._store.get(thread_id)
        if goal is None or not goal.is_active:
            return None
        return Continuation(
            thread_id=thread_id,
            steering_prompt=self._steering_prompt(goal),
            goal=goal,
        )

    def resume(self, thread_id: str) -> Optional[Continuation]:
        """On restart, re-read the durable row and re-arm the idle loop.

        Returns a Continuation if the goal is still active, else None.
        """
        return self.maybe_continue(thread_id)

    def resume_all(self) -> list[Continuation]:
        """Resume all active goals (e.g. after a process restart)."""
        continuations = []
        for goal in self._store.list_active():
            if goal.thread_id not in self._active_turns:
                continuations.append(
                    Continuation(
                        thread_id=goal.thread_id,
                        steering_prompt=self._steering_prompt(goal),
                        goal=goal,
                    )
                )
        return continuations

    def _steering_prompt(self, goal: Goal) -> str:
        return ANTI_DRIFT_TEMPLATE.format(
            objective=goal.objective,
            status=goal.status.value,
            usage=goal.usage.tokens,
            wall_ms=goal.usage.wall_ms,
        )

    # ------------------------------------------------------------------ audit helpers

    def mark_complete(self, thread_id: str, evidence: str) -> Goal:
        """Completion audit: only mark complete with evidence."""
        goal = self._store.get(thread_id)
        if goal is None:
            raise KeyError(f"Goal not found for thread {thread_id}")
        # Evidence is captured in the blocked/last_reason field temporarily to
        # keep the schema simple; in production this would be a separate table.
        return self._store.transition(thread_id, GoalStatus.COMPLETE, reason=evidence)

    def mark_blocked(self, thread_id: str, reason: str) -> Goal:
        """Blocked audit: only mark blocked after 3 consecutive blocked turns.

        Consecutive blocking increments the counter. Non-blocking turns reset it.
        """
        goal = self._store.get(thread_id)
        if goal is None:
            raise KeyError(f"Goal not found for thread {thread_id}")

        new_count = goal.blocked_count + 1

        if new_count >= self.BLOCKED_THRESHOLD:
            return self._store.transition(thread_id, GoalStatus.BLOCKED, reason=reason)

        # Not enough consecutive blocked turns yet; just record the reason
        # by updating the row directly. We reuse blocked_count to count
        # consecutive blocking observations even before status flips.
        goal.blocked_count = new_count
        goal.last_blocked_reason = reason
        goal.updated_at = datetime.now(timezone.utc)
        self._store.save(goal)
        return goal

    def unblock(self, thread_id: str) -> Goal:
        """Move a blocked goal back to active, resetting the blocked counter.

        Also resets the counter when called on a goal that has observed
        blocking turns but has not yet flipped to BLOCKED.
        """
        goal = self._store.get(thread_id)
        if goal is None:
            raise KeyError(f"Goal not found for thread {thread_id}")
        goal.blocked_count = 0
        goal.last_blocked_reason = None
        goal.updated_at = datetime.now(timezone.utc)
        if goal.status == GoalStatus.ACTIVE:
            self._store.save(goal)
            return goal
        return self._store.transition(thread_id, GoalStatus.ACTIVE)
