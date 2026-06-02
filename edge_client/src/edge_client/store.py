"""SQLite-backed face cache and offline check-in queue."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS faces (
    attendance_device_id TEXT PRIMARY KEY,
    employee TEXT NOT NULL,
    embedding TEXT NOT NULL,
    model_version TEXT,
    modified TEXT
);
CREATE TABLE IF NOT EXISTS checkin_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    edge_id TEXT NOT NULL
);
"""


class Store:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_faces(self, rows: list[dict]) -> None:
        with self._conn() as c:
            c.executemany(
                """INSERT INTO faces
                   (attendance_device_id, employee, embedding, model_version, modified)
                   VALUES (:attendance_device_id, :employee, :embedding, :model_version, :modified)
                   ON CONFLICT(attendance_device_id) DO UPDATE SET
                     employee=excluded.employee, embedding=excluded.embedding,
                     model_version=excluded.model_version, modified=excluded.modified""",
                rows,
            )

    def all_faces(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM faces")]

    def max_modified(self) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT MAX(modified) AS m FROM faces").fetchone()
            return row["m"]

    def enqueue_checkin(self, device_id: str, timestamp: str, edge_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO checkin_queue (device_id, timestamp, edge_id) VALUES (?, ?, ?)",
                (device_id, timestamp, edge_id),
            )

    def pending_checkins(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM checkin_queue ORDER BY id")]

    def delete_checkin(self, row_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM checkin_queue WHERE id = ?", (row_id,))
