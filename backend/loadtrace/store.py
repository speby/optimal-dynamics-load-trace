"""SQLite store shaped like the DynamoDB design.

events        ~ load timeline table: partition key load_id, sort key event_time. Append-only.
external_ids  ~ GSI on external IDs: (system, external_id) -> load_id.
"""

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCHEMA = """
CREATE TABLE events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    load_id    TEXT NOT NULL,
    event_time TEXT NOT NULL,
    stage      TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('ok', 'fail')),
    detail     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX events_by_load ON events (load_id, event_time);

-- Not unique per external ID: a truck's ELD unit maps to many loads over time,
-- and a DynamoDB GSI doesn't enforce uniqueness either.
CREATE TABLE external_ids (
    system      TEXT NOT NULL,
    external_id TEXT NOT NULL,
    load_id     TEXT NOT NULL,
    PRIMARY KEY (system, external_id, load_id)
);
CREATE INDEX external_ids_by_load ON external_ids (load_id);
"""


@dataclass(frozen=True)
class Event:
    load_id: str
    event_time: datetime
    stage: str
    status: str
    detail: dict[str, Any]


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        # One connection shared by FastAPI's worker threads. check_same_thread=False only turns
        # off SQLite's guard; the lock is what makes sharing safe. (Production: DynamoDB client.)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript(SCHEMA)

    def _query(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self.lock:
            return self.db.execute(sql, params).fetchall()

    def append(self, event: Event) -> None:
        self._query(
            "INSERT INTO events (load_id, event_time, stage, status, detail) VALUES (?, ?, ?, ?, ?)",
            (event.load_id, event.event_time.isoformat(), event.stage, event.status, json.dumps(event.detail)),
        )

    def link(self, load_id: str, system: str, external_id: str) -> None:
        self._query(
            "INSERT OR IGNORE INTO external_ids (system, external_id, load_id) VALUES (?, ?, ?)",
            (system, external_id, load_id),
        )

    def events_for(self, load_id: str) -> list[Event]:
        rows = self._query(
            "SELECT load_id, event_time, stage, status, detail FROM events WHERE load_id = ? ORDER BY event_time, seq",
            (load_id,),
        )
        return [Event(r[0], datetime.fromisoformat(r[1]), r[2], r[3], json.loads(r[4])) for r in rows]

    def external_ids_for(self, load_id: str) -> dict[str, str]:
        rows = self._query(
            "SELECT system, external_id FROM external_ids WHERE load_id = ?", (load_id,)
        )
        return dict(rows)

    def find(self, query: str = "") -> list[str]:
        """Internal load IDs matching the query against the internal ID or any external ID."""
        like = f"%{query.strip()}%"
        rows = self._query(
            """
            SELECT DISTINCT load_id FROM events WHERE load_id LIKE ?
            UNION
            SELECT DISTINCT load_id FROM external_ids WHERE external_id LIKE ?
            ORDER BY load_id
            """,
            (like, like),
        )
        return [r[0] for r in rows]
