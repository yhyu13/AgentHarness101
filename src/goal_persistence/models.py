from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class GoalStatus(str, enum.Enum):
    """Status machine for a persistent goal.

    Active → { Paused, Blocked, UsageLimited, BudgetLimited, Complete }
    Complete and BudgetLimited are terminal.
    """

    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    USAGE_LIMITED = "usage_limited"
    BUDGET_LIMITED = "budget_limited"
    COMPLETE = "complete"
    QUARANTINED = "quarantined"  # set aside after repeated failures; re-armable

    @property
    def is_terminal(self) -> bool:
        return self in (GoalStatus.BUDGET_LIMITED, GoalStatus.COMPLETE)


# Allowed transitions. Any other change is rejected.
ALLOWED_TRANSITIONS: dict[GoalStatus, set[GoalStatus]] = {
    GoalStatus.ACTIVE: {
        GoalStatus.PAUSED,
        GoalStatus.BLOCKED,
        GoalStatus.USAGE_LIMITED,
        GoalStatus.BUDGET_LIMITED,
        GoalStatus.COMPLETE,
        GoalStatus.QUARANTINED,
    },
    GoalStatus.PAUSED: {GoalStatus.ACTIVE, GoalStatus.COMPLETE},
    GoalStatus.BLOCKED: {GoalStatus.ACTIVE, GoalStatus.PAUSED, GoalStatus.COMPLETE},
    GoalStatus.USAGE_LIMITED: {GoalStatus.ACTIVE, GoalStatus.PAUSED},
    GoalStatus.QUARANTINED: {GoalStatus.ACTIVE},  # re-armable after operator review
    # Terminal states have no outgoing transitions.
    GoalStatus.BUDGET_LIMITED: set(),
    GoalStatus.COMPLETE: set(),
}


class TransitionError(ValueError):
    """Raised when a goal status transition is not allowed."""


@dataclass(frozen=True, slots=True)
class Usage:
    """Cumulative usage for a goal."""

    tokens_input: int = 0
    tokens_cached_input: int = 0
    tokens_output: int = 0
    wall_ms: int = 0  # wall-clock time in milliseconds

    @property
    def tokens(self) -> int:
        """Accounted token delta: input − cached_input + output."""
        return (self.tokens_input - self.tokens_cached_input) + self.tokens_output

    def add(self, other: Usage) -> Usage:
        return Usage(
            tokens_input=self.tokens_input + other.tokens_input,
            tokens_cached_input=self.tokens_cached_input + other.tokens_cached_input,
            tokens_output=self.tokens_output + other.tokens_output,
            wall_ms=self.wall_ms + other.wall_ms,
        )


@dataclass(slots=True)
class Goal:
    """Durable goal row keyed by thread/context ID."""

    thread_id: str
    objective: str
    status: GoalStatus = GoalStatus.ACTIVE
    budget_tokens: Optional[int] = None
    budget_wall_ms: Optional[int] = None
    usage: Usage = field(default_factory=Usage)
    blocked_count: int = 0
    last_blocked_reason: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def with_status(self, new_status: GoalStatus, reason: Optional[str] = None) -> Goal:
        # Allow no-op self-transitions for idempotent operations.
        if new_status == self.status:
            if reason is not None:
                self.last_blocked_reason = reason
            self.updated_at = datetime.now(timezone.utc)
            return self
        if new_status not in ALLOWED_TRANSITIONS.get(self.status, set()):
            raise TransitionError(
                f"Invalid transition from {self.status.value} to {new_status.value}"
            )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        if new_status == GoalStatus.BLOCKED:
            self.blocked_count += 1
            self.last_blocked_reason = reason
        elif new_status == GoalStatus.COMPLETE:
            # Capture completion evidence; field reused to keep schema simple.
            self.last_blocked_reason = reason
            self.blocked_count = 0
        else:
            # Reset blocked counter when leaving blocked state.
            self.blocked_count = 0
            self.last_blocked_reason = None
        return self

    def apply_usage(self, delta: Usage) -> Goal:
        self.usage = self.usage.add(delta)
        self.updated_at = datetime.now(timezone.utc)
        # Budget auto-transition inside the accounting write.
        if self.budget_tokens is not None and self.usage.tokens > self.budget_tokens:
            self.status = GoalStatus.BUDGET_LIMITED
            self.updated_at = datetime.now(timezone.utc)
        if self.budget_wall_ms is not None and self.usage.wall_ms > self.budget_wall_ms:
            self.status = GoalStatus.BUDGET_LIMITED
            self.updated_at = datetime.now(timezone.utc)
        return self

    @property
    def is_active(self) -> bool:
        return self.status == GoalStatus.ACTIVE

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal
