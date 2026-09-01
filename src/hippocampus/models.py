from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True, slots=True)
class MemoryFact:
    """A single durable fact learned from a task trajectory.

    ``correct`` is the learned verdict: False marks a fact the agent should stop
    repeating. ``evidence`` ties the fact back to the trajectory that produced it.
    """

    key: str
    value: str
    correct: bool = True
    evidence: str = ""
    source: str = ""


@dataclass(slots=True)
class TrajectoryStep:
    """One step in a task trajectory: an action, its outcome, and the important
    observation to index."""

    action: str
    outcome: str
    important: str = ""
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "outcome": self.outcome,
            "important": self.important,
            "at": self.at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrajectoryStep":
        return cls(
            action=data["action"],
            outcome=data["outcome"],
            important=data.get("important", ""),
            at=datetime.fromisoformat(data["at"]),
        )


@dataclass(slots=True)
class Trajectory:
    """A task run: ordered steps plus the facts it produced."""

    task_id: str
    steps: list[TrajectoryStep] = field(default_factory=list)
    facts: list[MemoryFact] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def add_step(self, step: TrajectoryStep) -> None:
        self.steps.append(step)

    def add_fact(self, fact: MemoryFact) -> None:
        self.facts.append(fact)

    def finish(self) -> None:
        if self.finished_at is None:
            self.finished_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "steps": [s.to_dict() for s in self.steps],
            "facts": [f.__dict__ for f in self.facts],
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trajectory":
        traj = cls(
            task_id=data["task_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            finished_at=(
                datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None
            ),
        )
        traj.steps = [TrajectoryStep.from_dict(s) for s in data.get("steps", [])]
        traj.facts = [
            MemoryFact(
                key=f["key"],
                value=f["value"],
                correct=f.get("correct", True),
                evidence=f.get("evidence", ""),
                source=f.get("source", ""),
            )
            for f in data.get("facts", [])
        ]
        return traj


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """What a replay produces: the trajectory plus the important content it indexed."""

    trajectory: Trajectory
    important_lines: list[str]
