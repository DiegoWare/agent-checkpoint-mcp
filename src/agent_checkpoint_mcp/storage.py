"""SQLite persistence for checkpoints.

A single global database with a `project` column keys checkpoints by project
root, so nothing is written inside user repos. WAL mode + busy_timeout allow
several agents (e.g. Claude Code and Cursor on the same machine) to write
concurrently.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .project import db_path

VALID_STATUSES = ("in_progress", "done", "blocked")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project TEXT NOT NULL,
  session_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'manual',
  plan TEXT NOT NULL,
  current_step INTEGER NOT NULL,
  total_steps INTEGER NOT NULL,
  step_status TEXT NOT NULL,
  what_was_done TEXT NOT NULL,
  what_remains TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_checkpoints_project_created
  ON checkpoints(project, created_at DESC, id DESC);
"""


@dataclass(frozen=True)
class Checkpoint:
    id: int
    project: str
    session_id: str
    created_at: str
    kind: str
    plan: str
    current_step: int
    total_steps: int
    step_status: str
    what_was_done: str
    what_remains: str


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Storage:
    def __init__(self, path: Path | None = None):
        self._path = path or db_path()
        self._conn = sqlite3.connect(self._path, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def save(
        self,
        *,
        project: str,
        session_id: str,
        plan: str,
        current_step: int,
        total_steps: int,
        step_status: str,
        what_was_done: str,
        what_remains: str,
        kind: str = "manual",
    ) -> Checkpoint:
        if step_status not in VALID_STATUSES:
            raise ValueError(
                f"step_status must be one of {VALID_STATUSES}, got {step_status!r}"
            )
        created_at = _utcnow()
        cur = self._conn.execute(
            """INSERT INTO checkpoints
               (project, session_id, created_at, kind, plan, current_step,
                total_steps, step_status, what_was_done, what_remains)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project, session_id, created_at, kind, plan, current_step,
             total_steps, step_status, what_was_done, what_remains),
        )
        self._conn.commit()
        return self.get_by_id(cur.lastrowid)

    def get_by_id(self, checkpoint_id: int) -> Checkpoint:
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no checkpoint with id {checkpoint_id}")
        return Checkpoint(**dict(row))

    def latest(self, project: str) -> Checkpoint | None:
        row = self._conn.execute(
            """SELECT * FROM checkpoints WHERE project = ?
               ORDER BY created_at DESC, id DESC LIMIT 1""",
            (project,),
        ).fetchone()
        return Checkpoint(**dict(row)) if row else None

    def list(self, project: str, limit: int = 20) -> list[Checkpoint]:
        rows = self._conn.execute(
            """SELECT * FROM checkpoints WHERE project = ?
               ORDER BY created_at DESC, id DESC LIMIT ?""",
            (project, limit),
        ).fetchall()
        return [Checkpoint(**dict(r)) for r in rows]

    def count(self, project: str) -> int:
        (n,) = self._conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE project = ?", (project,)
        ).fetchone()
        return n

    def clear(self, project: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM checkpoints WHERE project = ?", (project,)
        )
        self._conn.commit()
        return cur.rowcount
