from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from goal_persistence.models import Goal, GoalStatus, Usage


SCHEMA = """
CREATE TABLE IF NOT EXISTS thread_goals (
    thread_id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    status TEXT NOT NULL,
    budget_tokens INTEGER,
    budget_wall_ms INTEGER,
    usage TEXT NOT NULL DEFAULT '{}',
    blocked_count INTEGER NOT NULL DEFAULT 0,
    last_blocked_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turn_in_flight (
    thread_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    status TEXT NOT NULL,
    outcome TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    rounds INTEGER NOT NULL DEFAULT 0,
    usage_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def _serialize_usage(usage: Usage) -> str:
    return json.dumps(
        {
            "tokens_input": usage.tokens_input,
            "tokens_cached_input": usage.tokens_cached_input,
            "tokens_output": usage.tokens_output,
            "wall_ms": usage.wall_ms,
        }
    )


def _deserialize_usage(raw: str) -> Usage:
    data = json.loads(raw)
    return Usage(
        tokens_input=data.get("tokens_input", 0),
        tokens_cached_input=data.get("tokens_cached_input", 0),
        tokens_output=data.get("tokens_output", 0),
        wall_ms=data.get("wall_ms", 0),
    )


def _row_to_goal(row: sqlite3.Row) -> Goal:
    return Goal(
        thread_id=row["thread_id"],
        objective=row["objective"],
        status=GoalStatus(row["status"]),
        budget_tokens=row["budget_tokens"],
        budget_wall_ms=row["budget_wall_ms"],
        usage=_deserialize_usage(row["usage"]),
        blocked_count=row["blocked_count"],
        last_blocked_reason=row["last_blocked_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class GoalStore:
    """SQLite-backed durable store for persistent goals."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._ensure_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def create(self, goal: Goal) -> Goal:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO thread_goals (
                    thread_id, objective, status, budget_tokens, budget_wall_ms,
                    usage, blocked_count, last_blocked_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    goal.thread_id,
                    goal.objective,
                    goal.status.value,
                    goal.budget_tokens,
                    goal.budget_wall_ms,
                    _serialize_usage(goal.usage),
                    goal.blocked_count,
                    goal.last_blocked_reason,
                    goal.created_at.isoformat(),
                    goal.updated_at.isoformat(),
                ),
            )
            conn.commit()
        return goal

    def get(self, thread_id: str) -> Optional[Goal]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM thread_goals WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        return _row_to_goal(row) if row else None

    def _persist(self, goal: Goal) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE thread_goals SET
                    objective = ?, status = ?, budget_tokens = ?, budget_wall_ms = ?,
                    usage = ?, blocked_count = ?, last_blocked_reason = ?,
                    updated_at = ?
                WHERE thread_id = ?
                """,
                (
                    goal.objective,
                    goal.status.value,
                    goal.budget_tokens,
                    goal.budget_wall_ms,
                    _serialize_usage(goal.usage),
                    goal.blocked_count,
                    goal.last_blocked_reason,
                    goal.updated_at.isoformat(),
                    goal.thread_id,
                ),
            )
            conn.commit()

    def transition(
        self, thread_id: str, new_status: GoalStatus, reason: Optional[str] = None
    ) -> Goal:
        goal = self.get(thread_id)
        if goal is None:
            raise KeyError(f"Goal not found for thread {thread_id}")
        goal.with_status(new_status, reason=reason)
        self._persist(goal)
        return goal

    def apply_usage(self, thread_id: str, delta: Usage) -> Goal:
        goal = self.get(thread_id)
        if goal is None:
            raise KeyError(f"Goal not found for thread {thread_id}")
        goal.apply_usage(delta)
        self._persist(goal)
        return goal

    def save(self, goal: Goal) -> Goal:
        """Upsert a goal row. Used by the runtime to flush state."""
        existing = self.get(goal.thread_id)
        if existing is None:
            return self.create(goal)
        self._persist(goal)
        return goal

    def delete(self, thread_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM thread_goals WHERE thread_id = ?", (thread_id,))
            conn.commit()
            return cur.rowcount > 0

    def list_active(self) -> list[Goal]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM thread_goals WHERE status = ?",
                (GoalStatus.ACTIVE.value,),
            ).fetchall()
        return [_row_to_goal(row) for row in rows]

    # ------------------------------------------------------------------ in-flight marker (C1/C18)

    def mark_in_flight(self, thread_id: str, started_at: datetime) -> None:
        """Record that a turn was started but not yet flushed."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO turn_in_flight (thread_id, started_at) VALUES (?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET started_at = excluded.started_at
                """,
                (thread_id, started_at.isoformat()),
            )
            conn.commit()

    def clear_in_flight(self, thread_id: str) -> bool:
        """Drop the durable in-flight marker; True if a marker was removed."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM turn_in_flight WHERE thread_id = ?", (thread_id,))
            conn.commit()
            return cur.rowcount > 0

    def list_in_flight(self) -> list[str]:
        """Thread ids with an (possibly stale) durable in-flight turn marker."""
        with self._connect() as conn:
            rows = conn.execute("SELECT thread_id FROM turn_in_flight").fetchall()
        return [row["thread_id"] for row in rows]

    def get_in_flight(self, thread_id: str) -> Optional[dict[str, str]]:
        """The durable in-flight marker for a thread, if present."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT thread_id, started_at FROM turn_in_flight WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ run history ledger (C3)

    def record_run(
        self,
        thread_id: str,
        status: str,
        outcome: str,
        summary: str = "",
        rounds: int = 0,
        usage_tokens: int = 0,
        created_at: datetime | None = None,
    ) -> None:
        """Append one outcome row to the durable run ledger."""
        stamp = (created_at or datetime.now(timezone.utc)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_history (
                    thread_id, status, outcome, summary, rounds, usage_tokens, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (thread_id, status, outcome, summary, rounds, usage_tokens, stamp),
            )
            conn.commit()

    def list_runs(self, thread_id: str | None = None, limit: int = 100) -> list[dict[str, object]]:
        """Most-recent-first run ledger rows, optionally filtered to one thread."""
        query = (
            "SELECT thread_id, status, outcome, summary, rounds, usage_tokens, created_at "
            "FROM run_history"
        )
        params: tuple = ()
        if thread_id is not None:
            query += " WHERE thread_id = ?"
            params = (thread_id,)
        query += " ORDER BY id DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, (*params, limit)).fetchall()
        return [dict(row) for row in rows]
