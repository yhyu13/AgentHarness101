from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Approval(str, Enum):
    """Human-in-the-loop decision."""

    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class ActionRequest:
    """A proposed action that needs a permission decision."""

    action: str
    target: str
    risk: str


@dataclass(frozen=True, slots=True)
class Decision:
    """The decision for an action request."""

    approval: Approval
    reason: str = ""


_HIGH_RISK_ACTIONS = frozenset({"deploy", "delete", "drop", "purge", "format", "rm", "rmdir"})


@dataclass
class SafetyGuard:
    """Layer-M6 safety: RBAC roles + high-risk HITL + prompt-injection marker.

    - ``request`` evaluates an action against the active role's allowlist; high-risk
      actions require human approval.
    - ``check_prompt`` detects the simplest prompt-injection shape (a "system override"
      instruction embedded in content) and flags it as untrusted.
    """

    role: str = "default"
    _role_allowlist: dict[str, set[str]] = field(
        default_factory=lambda: {
            "default": {"read"},
            "engineer": {"read", "write", "run_test"},
            "admin": {"read", "write", "run_test", "deploy"},
        }
    )

    def request(self, action: str, target: str, risk: str = "low") -> Decision:
        allowed = action in self._role_allowlist.get(self.role, set())
        if not allowed:
            return Decision(Approval.DENIED, f"action {action} not allowed for role {self.role}")
        if risk == "high" or action in _HIGH_RISK_ACTIONS:
            # High-risk actions always require a human decision — the caller's risk
            # label cannot downgrade an intrinsically high-risk action.
            return Decision(Approval.PENDING, "human approval required for high-risk action")
        return Decision(Approval.APPROVED)

    def approve(self, decision: Decision) -> Decision:
        if decision.approval != Approval.PENDING:
            return decision
        return Decision(Approval.APPROVED, "human approved")

    def check_prompt(self, content: str) -> bool:
        """Return True if the content looks like a prompt-injection attempt."""
        markers = [
            "ignore previous instructions",
            "ignore all previous instructions",
            "ignore all instructions",
            "ignore your instructions",
            "you are now",
        ]
        # Normalize whitespace so "Ignore   ALL Previous Instructions" still matches.
        lowered = re.sub(r"\s+", " ", content.lower())
        return any(m in lowered for m in markers)
