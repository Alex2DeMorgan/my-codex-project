"""Core automation logic for the desktop task automation application.

This module contains the reusable data structures and classes that the
front-end and recorder modules rely on.  The goal is to keep everything that
is responsible for executing recorded actions in a single place so that the
logic can be reused both from the graphical interface and from future command
line tools or scheduled jobs.

The actual mouse and keyboard execution relies on optional third-party
libraries (``pynput`` for mouse/keyboard and ``pyperclip`` for clipboard
access).  The module is written in a way that gracefully degrades when those
libraries are not available on the target machine: the actions will still be
queued and logged, but the application will simply log a warning instead of
raising exceptions.
"""

from dataclasses import dataclass, field
from datetime import datetime
import logging
import threading
import time
from typing import List, Optional, Sequence

from database import RekordStorage

try:  # pragma: no cover - the optional dependency might not be installed
    from pynput import keyboard, mouse
except Exception:  # pragma: no cover - protect against missing library
    keyboard = None
    mouse = None

try:  # pragma: no cover - optional dependency
    import pyperclip
except Exception:  # pragma: no cover
    pyperclip = None


logger = logging.getLogger(__name__)


@dataclass
class Action:
    """Base data structure for any recorded automation action."""

    timestamp: float
    description: str

    def execute(self) -> None:
        """Execute the action using the available backends.

        Subclasses override :meth:`_execute_impl` to provide their specific
        automation logic.  The public :meth:`execute` method provides a thin
        layer that catches backend errors and turns them into log messages.
        """

        logger.debug("Executing action %s", self.description)
        try:
            self._execute_impl()
        except Exception:  # pragma: no cover - we only log errors here
            logger.exception("Failed to execute action: %s", self.description)

    # The default implementation does nothing.  Subclasses are expected to
    # override this method.
    def _execute_impl(self) -> None:  # pragma: no cover - interface only
        pass


@dataclass
class MouseMoveAction(Action):
    x: int = 0
    y: int = 0

    def _execute_impl(self) -> None:  # pragma: no cover - depends on backend
        if mouse is None:
            logger.warning("Mouse backend is not available; skipping move")
            return
        controller = mouse.Controller()
        controller.position = (self.x, self.y)


@dataclass
class MouseClickAction(Action):
    button: str = "left"
    pressed: bool = True
    x: Optional[int] = None
    y: Optional[int] = None

    def _execute_impl(self) -> None:  # pragma: no cover - depends on backend
        if mouse is None:
            logger.warning("Mouse backend is not available; skipping click")
            return
        controller = mouse.Controller()
        if self.x is not None and self.y is not None:
            controller.position = (self.x, self.y)
        button = getattr(mouse.Button, self.button, mouse.Button.left)
        if self.pressed:
            controller.press(button)
        else:
            controller.release(button)


@dataclass
class MouseScrollAction(Action):
    dx: int = 0
    dy: int = 0
    x: Optional[int] = None
    y: Optional[int] = None

    def _execute_impl(self) -> None:  # pragma: no cover - depends on backend
        if mouse is None:
            logger.warning("Mouse backend is not available; skipping scroll")
            return
        controller = mouse.Controller()
        if self.x is not None and self.y is not None:
            controller.position = (self.x, self.y)
        controller.scroll(self.dx, self.dy)


@dataclass
class KeyboardAction(Action):
    key: str = ""
    pressed: bool = True

    def _execute_impl(self) -> None:  # pragma: no cover - depends on backend
        if keyboard is None:
            logger.warning("Keyboard backend is not available; skipping key")
            return
        controller = keyboard.Controller()
        key_obj = getattr(keyboard.Key, self.key, None)
        if key_obj is None:
            key_obj = self.key
        if self.pressed:
            controller.press(key_obj)
        else:
            controller.release(key_obj)


@dataclass
class ClipboardAction(Action):
    value: str = ""

    def _execute_impl(self) -> None:  # pragma: no cover - depends on backend
        if pyperclip is None:
            logger.warning(
                "Pyperclip is not available; cannot update the clipboard"
            )
            return
        pyperclip.copy(self.value)


class AutomationManager:
    """Coordinate recorded actions and play them back when requested."""

    def __init__(self, storage: Optional[RekordStorage] = None) -> None:
        self.storage = storage or RekordStorage()
        self._records: List["Rekord"] = list(self.storage.load())
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        logger.info(
            "AutomationManager initialised with %d stored records", len(self._records)
        )

    # A small import at runtime to avoid a circular dependency.
    def add_record(self, record: "Rekord") -> None:
        logger.info("Adding new record '%s' with %d actions", record.name, len(record.actions))
        self._records.append(record)
        self.storage.save_all(self._records)

    @property
    def records(self) -> Sequence["Rekord"]:
        return tuple(self._records)

    def clear(self) -> None:
        logger.info("Clearing %d stored records", len(self._records))
        self._records.clear()
        self.storage.clear()

    def playback(self, record: "Rekord", speed: float = 1.0) -> None:
        """Play back all actions from *record* on a background thread."""

        if self._playback_thread and self._playback_thread.is_alive():
            logger.warning("Playback already in progress; ignoring new request")
            return

        actions = self._convert_actions(record)
        logger.info("Starting playback for '%s' (%d actions)", record.name, len(actions))
        self._stop_event.clear()

        def _runner() -> None:
            last_timestamp: Optional[float] = None
            for action in actions:
                if self._stop_event.is_set():
                    logger.info("Playback interrupted for '%s'", record.name)
                    break
                if last_timestamp is not None:
                    delay = (action.timestamp - last_timestamp) / max(speed, 0.01)
                    if delay > 0:
                        logger.debug("Sleeping %.2fs before next action", delay)
                        time.sleep(delay)
                action.execute()
                last_timestamp = action.timestamp
            logger.info("Playback completed for '%s'", record.name)

        self._playback_thread = threading.Thread(target=_runner, daemon=True)
        self._playback_thread.start()

    def stop_playback(self) -> None:
        if not self._playback_thread:
            return
        logger.info("Stopping playback")
        self._stop_event.set()
        self._playback_thread.join(timeout=1)
        self._playback_thread = None

    @staticmethod
    def _to_int(value: object, default: int = 0) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return default
            try:
                if "." in value or "e" in value.lower():
                    return int(float(value))
                return int(value)
            except ValueError:
                logger.debug("Failed to convert '%s' to int; using default %s", value, default)
        return default

    @staticmethod
    def _to_bool(value: object, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            value_lower = value.strip().lower()
            if not value_lower:
                return default
            if value_lower in {"true", "1", "yes", "pressed", "down", "on"}:
                return True
            if value_lower in {"false", "0", "no", "released", "up", "off"}:
                return False
        return default

    @staticmethod
    def _to_str(value: object, default: str = "") -> str:
        if value is None:
            return default
        return str(value)

    @classmethod
    def _optional_int(cls, value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return cls._to_int(value)

    @classmethod
    def _convert_actions(cls, record: "Rekord") -> List[Action]:
        actions: List[Action] = []
        for item in record.actions:
            if isinstance(item, Action):
                actions.append(item)
                continue
            if not isinstance(item, RekordAction):
                logger.debug("Skipping unsupported action type: %s", type(item))
                continue
            description = f"{item.event_type}: {item.payload}"
            if item.event_type == "mouse_move":
                actions.append(
                    MouseMoveAction(
                        timestamp=item.timestamp,
                        description=description,
                        x=cls._to_int(item.payload.get("x")),
                        y=cls._to_int(item.payload.get("y")),
                    )
                )
            elif item.event_type == "mouse_click":
                actions.append(
                    MouseClickAction(
                        timestamp=item.timestamp,
                        description=description,
                        button=cls._to_str(item.payload.get("button", "left"), "left"),
                        pressed=cls._to_bool(item.payload.get("pressed", True)),
                        x=cls._optional_int(item.payload.get("x")),
                        y=cls._optional_int(item.payload.get("y")),
                    )
                )
            elif item.event_type == "mouse_scroll":
                actions.append(
                    MouseScrollAction(
                        timestamp=item.timestamp,
                        description=description,
                        dx=cls._to_int(item.payload.get("dx", 0)),
                        dy=cls._to_int(item.payload.get("dy", 0)),
                        x=cls._optional_int(item.payload.get("x")),
                        y=cls._optional_int(item.payload.get("y")),
                    )
                )
            elif item.event_type == "keyboard":
                actions.append(
                    KeyboardAction(
                        timestamp=item.timestamp,
                        description=description,
                        key=cls._to_str(item.payload.get("key")),
                        pressed=cls._to_bool(item.payload.get("pressed", True)),
                    )
                )
            elif item.event_type == "clipboard":
                actions.append(
                    ClipboardAction(
                        timestamp=item.timestamp,
                        description=description,
                        value=str(item.payload.get("value", "")),
                    )
                )
        return actions


# Import placed at the bottom to avoid circular dependencies during runtime
from recorder_tab import Rekord, RekordAction  # noqa: E402  # isort:skip

