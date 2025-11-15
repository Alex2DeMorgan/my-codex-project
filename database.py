"""Persistence helpers for storing and loading recorded automation sessions."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)


class RekordStorage:
    """Persist :class:`~recorder_tab.Rekord` objects to an SQLite database."""

    def __init__(self, path: Optional[Path] = None) -> None:
        default_path = Path.home() / ".automation_records.sqlite"
        self.path = Path(path) if path is not None else default_path
        self._lock = threading.Lock()
        self._ensure_parent_directory()
        self._initialise_schema()

    # ------------------------------------------------------------------
    def load(self) -> List["Rekord"]:
        """Load stored records from disk."""

        try:
            from recorder_tab import Rekord, RekordAction
        except ImportError:
            logger.exception("Recorder module is not available; cannot load records")
            return []

        with self._lock:
            connection = self._connect()
            try:
                cursor = connection.execute(
                    "SELECT id, name, created_at FROM records ORDER BY created_at ASC"
                )
                records: List[Rekord] = []
                for row in cursor.fetchall():
                    created_at = self._parse_datetime(row["created_at"])
                    rekord = Rekord(name=row["name"], created_at=created_at)

                    action_rows = connection.execute(
                        """
                        SELECT timestamp, event_type, payload
                        FROM actions
                        WHERE record_id = ?
                        ORDER BY id ASC
                        """,
                        (row["id"],),
                    )
                    for action_row in action_rows.fetchall():
                        payload = self._decode_payload(action_row["payload"])
                        rekord.actions.append(
                            RekordAction(
                                timestamp=float(action_row["timestamp"]),
                                event_type=str(action_row["event_type"]),
                                payload=payload,
                            )
                        )
                    records.append(rekord)
                logger.info("Loaded %d records from %s", len(records), self.path)
                return records
            except sqlite3.DatabaseError:
                logger.exception("Failed to load records from database: %s", self.path)
                return []
            finally:
                connection.close()

    def save_all(self, records: Iterable["Rekord"]) -> None:
        """Persist all provided records to disk in a single transaction."""

        with self._lock:
            connection = self._connect()
            try:
                connection.execute("DELETE FROM actions")
                connection.execute("DELETE FROM records")

                for record in records:
                    created_at = record.created_at.isoformat()
                    cursor = connection.execute(
                        "INSERT INTO records (name, created_at) VALUES (?, ?)",
                        (record.name, created_at),
                    )
                    record_id = cursor.lastrowid
                    if record_id is None:
                        record_id = connection.execute(
                            "SELECT last_insert_rowid()"
                        ).fetchone()[0]

                    for action in getattr(record, "actions", []):
                        payload = json.dumps(
                            getattr(action, "payload", {}),
                            ensure_ascii=False,
                        )
                        connection.execute(
                            """
                            INSERT INTO actions (record_id, timestamp, event_type, payload)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                record_id,
                                float(getattr(action, "timestamp", 0.0)),
                                str(getattr(action, "event_type", "")),
                                payload,
                            ),
                        )

                connection.commit()
            except sqlite3.DatabaseError:
                connection.rollback()
                logger.exception("Failed to persist Rekord storage to %s", self.path)
            finally:
                connection.close()

    def clear(self) -> None:
        """Remove all data from the storage."""

        with self._lock:
            connection = self._connect()
            try:
                connection.execute("DELETE FROM actions")
                connection.execute("DELETE FROM records")
                connection.commit()
            except sqlite3.DatabaseError:
                connection.rollback()
                logger.exception("Failed to clear Rekord storage at %s", self.path)
            finally:
                connection.close()

    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise_schema(self) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        record_id INTEGER NOT NULL,
                        timestamp REAL NOT NULL,
                        event_type TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        FOREIGN KEY(record_id) REFERENCES records(id) ON DELETE CASCADE
                    );
                    """
                )
                connection.commit()
            except sqlite3.DatabaseError:
                connection.rollback()
                logger.exception(
                    "Failed to initialise Rekord storage schema at %s", self.path
                )
            finally:
                connection.close()

    def _ensure_parent_directory(self) -> None:
        parent = self.path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("Failed to create Rekord storage directory: %s", parent)

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> datetime:
        if value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                logger.debug("Invalid datetime stored in database: %s", value)
        return datetime.utcnow()

    @staticmethod
    def _decode_payload(raw: Optional[str]) -> dict:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Failed to decode payload JSON: %s", raw)
            return {}


# Late import for type checking without creating circular dependencies
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from recorder_tab import Rekord

