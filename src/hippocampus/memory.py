from __future__ import annotations

from typing import Callable, Optional

from hippocampus.models import MemoryFact, ReplayResult, Trajectory, TrajectoryStep
from hippocampus.store import HippocampusStore


class Hippocampus:
    """Long-term memory with trajectory, index, cache, update, and replay.

    - ``record_step`` appends to a trajectory and indexes ``important`` content.
    - ``learn`` / ``unlearn`` / ``correct`` update the fact index (delete wrong, keep
      right).
    - ``replay`` re-reads a trajectory and returns its important content for
      retrospective review.
    """

    def __init__(self, store: HippocampusStore) -> None:
        self._store = store

    def start_trajectory(self, task_id: str) -> Trajectory:
        trajectory = Trajectory(task_id=task_id)
        self._store.save_trajectory(trajectory)
        return trajectory

    def record_step(
        self,
        trajectory: Trajectory,
        action: str,
        outcome: str,
        important: str = "",
    ) -> None:
        trajectory.add_step(TrajectoryStep(action=action, outcome=outcome, important=important))
        if important:
            self._store.upsert_fact(
                MemoryFact(
                    key=f"{trajectory.task_id}::{action}",
                    value=important,
                    correct=True,
                    evidence=f"{trajectory.task_id} trajectory",
                    source=action,
                )
            )
        self._store.save_trajectory(trajectory)

    def learn(self, key: str, value: str, correct: bool = True, evidence: str = "") -> None:
        self._store.upsert_fact(
            MemoryFact(key=key, value=value, correct=correct, evidence=evidence)
        )

    def unlearn(self, key: str) -> bool:
        """Delete a wrong/obsolete fact."""
        return self._store.forget_fact(key)

    def correct(self, key: str, value: str) -> None:
        """Learn the correct replacement for a fact."""
        self._store.upsert_fact(MemoryFact(key=key, value=value, correct=True))

    def get(self, key: str) -> Optional[MemoryFact]:
        return self._store.get_fact(key)

    def replay(self, task_id: str) -> Optional[ReplayResult]:
        trajectory = self._store.load_trajectory(task_id)
        if trajectory is None:
            return None
        important_lines = [
            step.important for step in trajectory.steps if step.important
        ]
        return ReplayResult(trajectory=trajectory, important_lines=important_lines)

    def retrospective(self) -> list[MemoryFact]:
        """Return the current set of correct facts for periodic review."""
        return self._store.correct_facts()

    def facts(self) -> list[MemoryFact]:
        """Return every learned fact (correct and incorrect) for self-review / retrieval."""
        return self._store.list_facts()
