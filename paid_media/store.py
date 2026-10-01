"""SQLite human-review state machine with optimistic locking and append-only audit entries."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

TRANSITIONS = {
    "Proposed": {"Approved", "Rejected"},
    "Approved": {"Testing", "Rejected"},
    "Testing": {"Completed", "Rejected"},
    "Rejected": set(),
    "Completed": set(),
}


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS recommendations (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Proposed',
                    version INTEGER NOT NULL DEFAULT 1, result TEXT, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, recommendation_id TEXT NOT NULL,
                    from_status TEXT, to_status TEXT NOT NULL, reviewer TEXT NOT NULL,
                    notes TEXT NOT NULL, occurred_at TEXT NOT NULL, result TEXT
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def sync(self, recommendations: list[dict]):
        with self.connection() as db:
            for r in recommendations:
                db.execute(
                    "INSERT OR IGNORE INTO recommendations(id,payload,updated_at) VALUES(?,?,?)",
                    (r["id"], json.dumps(r), datetime.now(UTC).isoformat()),
                )

    @staticmethod
    def decode(row):
        return {
            **json.loads(row["payload"]),
            "status": row["status"],
            "version": row["version"],
            "result": json.loads(row["result"]) if row["result"] else None,
            "updated_at": row["updated_at"],
        }

    def list(self):
        with self.connection() as db:
            return [self.decode(r) for r in db.execute("SELECT * FROM recommendations ORDER BY id")]

    def get(self, rid):
        with self.connection() as db:
            row = db.execute("SELECT * FROM recommendations WHERE id=?", (rid,)).fetchone()
            if row is None:
                raise KeyError(rid)
            return self.decode(row)

    def transition(self, rid: str, status: str, reviewer: str, notes: str, version: int, result=None):
        if not reviewer.strip() or not notes.strip():
            raise ValueError("Reviewer and rationale are required.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM recommendations WHERE id=?", (rid,)).fetchone()
            if row is None:
                raise KeyError(rid)
            if row["version"] != version:
                raise Conflict("Review changed since you loaded it; refresh before deciding.")
            if status not in TRANSITIONS.get(row["status"], set()):
                raise Conflict(f"Cannot transition {row['status']} to {status}.")
            if status == "Completed" and not result:
                raise ValueError("Test results are required before completion.")
            if result and status != "Completed":
                raise ValueError("Record final results when marking the test Completed.")
            timestamp = datetime.now(UTC).isoformat()
            encoded = json.dumps(result) if result else None
            db.execute(
                "UPDATE recommendations SET status=?, version=version+1, result=?, updated_at=? WHERE id=?",
                (status, encoded, timestamp, rid),
            )
            db.execute(
                "INSERT INTO audit(recommendation_id,from_status,to_status,reviewer,notes,occurred_at,result) "
                "VALUES(?,?,?,?,?,?,?)",
                (rid, row["status"], status, reviewer.strip(), notes.strip(), timestamp, encoded),
            )
        return self.get(rid)

    def history(self, rid):
        self.get(rid)
        with self.connection() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM audit WHERE recommendation_id=? ORDER BY event_id", (rid,))
            ]
