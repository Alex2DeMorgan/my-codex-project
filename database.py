"""Persistence helpers for storing and loading recorded automation sessions."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
import threading
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)


class RekordStorage:
    """Persist :class:`~recorder_tab.Rekord` objects to a JSON file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        default_path = Path.home() / ".automation_records.json"
        self.path = Path(path) if path is not None else default_path
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def load(self) -> List["Rekord"]:
        """Load stored records from disk.

        Errors while reading the file are logged and result in an empty list
        so the UI can continue to operate even if the file becomes corrupted.
        """

        if not self.path.exists():
            logger.debug("Rekord storage file does not exist: %s", self.path)
            return []

        try:
            raw_data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.exception("Failed to decode Rekord storage JSON: %s", self.path)
            return []
        except OSError:
            logger.exception("Failed to read Rekord storage: %s", self.path)
            return []

        records: List["Rekord"] = []
        for entry in raw_data:
            rekord = self._deserialize_rekord(entry)
            if rekord is not None:
                records.append(rekord)
        logger.info("Loaded %d records from %s", len(records), self.path)
        return records

    def save_all(self, records: Iterable["Rekord"]) -> None:
        """Persist all provided records to disk in a single JSON file."""

        serialised = [self._serialize_rekord(record) for record in records]
        self._ensure_parent_directory()
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")

        with self._lock:
            try:
                tmp_path.write_text(
                    json.dumps(serialised, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                tmp_path.replace(self.path)
            except OSError:
                logger.exception("Failed to persist Rekord storage to %s", self.path)

    def clear(self) -> None:
        """Remove the storage file if it exists."""

        with self._lock:
            try:
                if self.path.exists():
                    self.path.unlink()
            except OSError:
                logger.exception("Failed to clear Rekord storage at %s", self.path)

    # ------------------------------------------------------------------
    def _ensure_parent_directory(self) -> None:
        parent = self.path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("Failed to create Rekord storage directory: %s", parent)

    @staticmethod
    def _serialize_rekord(rekord: "Rekord") -> dict:
        return {
            "name": rekord.name,
            "created_at": rekord.created_at.isoformat(),
            "actions": [
                {
                    "timestamp": action.timestamp,
                    "event_type": action.event_type,
                    "payload": action.payload,
                }
                for action in getattr(rekord, "actions", [])
            ],
        }

    @staticmethod
    def _deserialize_rekord(payload: dict) -> Optional["Rekord"]:
        try:
            from recorder_tab import Rekord, RekordAction
        except ImportError:
            logger.exception("Recorder module is not available; cannot load records")
            return None

        try:
            created_at_raw = payload.get("created_at")
            created_at = (
                datetime.fromisoformat(created_at_raw)
                if created_at_raw
                else datetime.utcnow()
            )
            rekord = Rekord(name=str(payload.get("name", "")), created_at=created_at)

            for action_payload in payload.get("actions", []):
                rekord.actions.append(
                    RekordAction(
                        timestamp=float(action_payload.get("timestamp", 0.0)),
                        event_type=str(action_payload.get("event_type", "")),
                        payload=dict(action_payload.get("payload", {})),
                    )
                )
            return rekord
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to rebuild Rekord from payload: %s", payload)
            return None


# Late import for type checking without creating circular dependencies
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from recorder_tab import Rekord
