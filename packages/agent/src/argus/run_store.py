"""SQLite index for durable run metadata and on-disk artifacts."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class RunStore:
    """Keep searchable run metadata in SQLite while leaving large data on disk."""

    def __init__(self, artifact_root: str | Path):
        self.artifact_root = Path(artifact_root).resolve()
        self.runs_root = self.artifact_root / "runs"
        self.database_path = self.artifact_root / "runs.sqlite3"
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    target_url TEXT NOT NULL,
                    spec TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
        self._index_existing_runs()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=15000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _serialize_spec(value: Any) -> str:
        return (
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        )

    def _index_existing_runs(self) -> None:
        """Make completed CLI and fixture runs visible through the API too."""
        if not self.runs_root.is_dir():
            return
        with self._connect() as connection:
            for run_dir in self.runs_root.iterdir():
                state_path = run_dir / "state.json"
                if (
                    not run_dir.is_dir()
                    or not _SAFE_RUN_ID.fullmatch(run_dir.name)
                    or not state_path.is_file()
                ):
                    continue
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                target_url = str(state.get("target_url") or "")
                spec = self._serialize_spec(state.get("spec", ""))
                created_at = datetime.fromtimestamp(
                    state_path.stat().st_mtime, UTC
                ).isoformat()
                events_path = run_dir / "events.ndjson"
                if events_path.is_file():
                    try:
                        first_line = events_path.read_text(
                            encoding="utf-8"
                        ).splitlines()[0]
                        first_event = json.loads(first_line)
                        created_at = str(first_event.get("ts") or created_at)
                    except (OSError, IndexError, json.JSONDecodeError):
                        pass
                connection.execute(
                    """INSERT OR IGNORE INTO runs
                       (run_id, target_url, spec, status, created_at, updated_at)
                       VALUES (?, ?, ?, 'completed', ?, ?)""",
                    (run_dir.name, target_url, spec, created_at, created_at),
                )

    def create(self, run_id: str, target_url: str, spec: str) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO runs
                   (run_id, target_url, spec, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'queued', ?, ?)""",
                (run_id, target_url, spec, now, now),
            )

    def delete(self, run_id: str) -> bool:
        """Remove a run's index row and its artifact directory."""
        if not _SAFE_RUN_ID.fullmatch(run_id):
            return False
        with self._connect() as connection:
            deleted = connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,)).rowcount
        run_dir = (self.runs_root / run_id).resolve()
        if run_dir.parent == self.runs_root.resolve() and run_dir.is_dir():
            shutil.rmtree(run_dir, ignore_errors=True)
        return bool(deleted)

    def update(self, run_id: str, *, status: str, error: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, error = ?, updated_at = ? WHERE run_id = ?",
                (status, error, self._now(), run_id),
            )

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    def list(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, run_id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows], int(total)

    @staticmethod
    def is_terminal(status: str) -> bool:
        return status in _TERMINAL_STATUSES
