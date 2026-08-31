from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from hippocampus.models import MemoryFact, Trajectory


class HippocampusStore:
    """Durable long-term memory: trajectories on disk, plus an index of important facts.

    The "index" is bounded and always-loadable (one JSON line per fact); the full
    trajectory files are on-demand detail, matching the memory-persistence pattern.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._traj_dir = self._root / "trajectories"
        self._cache_dir = self._root / "cache"
        self._index_path = self._root / "memory_index.json"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self._traj_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ index

    def _read_index(self) -> dict[str, dict]:
        if not self._index_path.exists():
            return {}
        return json.loads(self._index_path.read_text(encoding="utf-8"))

    def _write_index(self, index: dict[str, dict]) -> None:
        self._index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def save_trajectory(self, trajectory: Trajectory) -> None:
        trajectory.finish()
        path = self._traj_dir / f"{trajectory.task_id}.json"
        path.write_text(
            json.dumps(trajectory.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_trajectory(self, task_id: str) -> Optional[Trajectory]:
        path = self._traj_dir / f"{task_id}.json"
        if not path.exists():
            return None
        return Trajectory.from_dict(json.loads(path.read_text(encoding="utf-8")))

    # ------------------------------------------------------------------ facts

    def upsert_fact(self, fact: MemoryFact) -> None:
        """Learn a fact into the index, and cache its value locally."""
        index = self._read_index()
        index[fact.key] = {
            "value": fact.value,
            "correct": fact.correct,
            "evidence": fact.evidence,
            "source": fact.source,
        }
        self._write_index(index)
        self._write_cache(fact.key, fact.value)

    def forget_fact(self, key: str) -> bool:
        """Delete a fact from the index and its cached value, as one operation."""
        index = self._read_index()
        if key not in index:
            return False
        del index[key]
        self._write_index(index)
        self._delete_cache(key)
        return True

    def get_fact(self, key: str) -> Optional[MemoryFact]:
        index = self._read_index()
        if key not in index:
            return None
        d = index[key]
        return MemoryFact(
            key=key,
            value=d["value"],
            correct=d.get("correct", True),
            evidence=d.get("evidence", ""),
            source=d.get("source", ""),
        )

    def list_facts(self) -> list[MemoryFact]:
        return [
            MemoryFact(
                key=k,
                value=d["value"],
                correct=d.get("correct", True),
                evidence=d.get("evidence", ""),
                source=d.get("source", ""),
            )
            for k, d in self._read_index().items()
        ]

    def correct_facts(self) -> list[MemoryFact]:
        return [f for f in self.list_facts() if f.correct]

    # ------------------------------------------------------------------ cache

    def _write_cache(self, key: str, value: str) -> None:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        (self._cache_dir / f"{safe}.txt").write_text(value, encoding="utf-8")

    def _delete_cache(self, key: str) -> None:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        path = self._cache_dir / f"{safe}.txt"
        if path.exists():
            path.unlink()

    def read_cache(self, key: str) -> Optional[str]:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        path = self._cache_dir / f"{safe}.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None
