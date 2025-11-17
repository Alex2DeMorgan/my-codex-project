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
from typing import Callable, List, Optional, Sequence, Tuple

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


try:  # pragma: no cover - Tk may be unavailable (e.g. headless envs)
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None


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

    def __init__(
        self,
        storage: Optional[RekordStorage] = None,
        screen_size_provider: Optional[Callable[[], Optional[Tuple[int, int]]]] = None,
    ) -> None:
        self.storage = storage or RekordStorage()
        self._records: List["Rekord"] = list(self.storage.load())
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._screen_size_provider = screen_size_provider or self._fallback_screen_size_provider
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

        screen_size = self._get_screen_size()
        actions = self._convert_actions(record, screen_size)
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

    @staticmethod
    def _to_float(value: object, default: float = 0.0) -> float:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return default
            try:
                return float(value)
            except ValueError:
                logger.debug("Failed to convert '%s' to float; using default %s", value, default)
        return default

    @classmethod
    def _optional_int(cls, value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return cls._to_int(value)

    def _convert_actions(
        self, record: "Rekord", screen_size: Optional[Tuple[int, int]]
    ) -> List[Action]:
        actions: List[Action] = []
        if screen_size is None:
            current_width = current_height = None
        else:
            current_width, current_height = screen_size
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
                        x=self._resolve_coordinate(
                            record, item.payload, "x", current_width
                        ),
                        y=self._resolve_coordinate(
                            record, item.payload, "y", current_height
                        ),
                    )
                )
            elif item.event_type == "mouse_click":
                actions.append(
                    MouseClickAction(
                        timestamp=item.timestamp,
                        description=description,
                        button=self._to_str(item.payload.get("button", "left"), "left"),
                        pressed=self._to_bool(item.payload.get("pressed", True)),
                        x=self._resolve_coordinate(
                            record, item.payload, "x", current_width, optional=True
                        ),
                        y=self._resolve_coordinate(
                            record, item.payload, "y", current_height, optional=True
                        ),
                    )
                )
            elif item.event_type == "mouse_scroll":
                actions.append(
                    MouseScrollAction(
                        timestamp=item.timestamp,
                        description=description,
                        dx=self._to_int(item.payload.get("dx", 0)),
                        dy=self._to_int(item.payload.get("dy", 0)),
                        x=self._resolve_coordinate(
                            record, item.payload, "x", current_width, optional=True
                        ),
                        y=self._resolve_coordinate(
                            record, item.payload, "y", current_height, optional=True
                        ),
                    )
                )
            elif item.event_type == "keyboard":
                actions.append(
                    KeyboardAction(
                        timestamp=item.timestamp,
                        description=description,
                        key=self._to_str(item.payload.get("key")),
                        pressed=self._to_bool(item.payload.get("pressed", True)),
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

    def _resolve_coordinate(
        self,
        record: "Rekord",
        payload: dict,
        axis: str,
        current_size: Optional[int],
        optional: bool = False,
    ) -> Optional[int]:
        key = axis
        norm_key = f"n{axis}"
        absolute_value = payload.get(key)
        ratio_value = payload.get(norm_key)
        ratio: Optional[float] = None

        if ratio_value is not None:
            ratio = self._to_float(ratio_value, default=-1.0)
            if ratio < 0:
                ratio = None
        elif absolute_value is not None:
            record_size = getattr(
                record,
                "screen_width" if axis == "x" else "screen_height",
                None,
            )
            if isinstance(record_size, (int, float)) and record_size:
                ratio = float(self._to_int(absolute_value)) / float(record_size)

        if ratio is not None and current_size:
            resolved = int(round(ratio * current_size))
            logger.debug(
                "Resolved %s coordinate using ratio %.4f -> %s (current size %s)",
                axis,
                ratio,
                resolved,
                current_size,
            )
            return resolved

        if absolute_value is not None:
            resolved = self._to_int(absolute_value)
            logger.debug("Resolved %s coordinate using absolute value %s", axis, resolved)
            return resolved

        return None if optional else 0

    def _get_screen_size(self) -> Optional[Tuple[int, int]]:
        try:
            size = self._screen_size_provider()
        except Exception:  # pragma: no cover - defensive logging
            logger.debug("Screen size provider raised an exception", exc_info=True)
            return None
        if not size:
            return None
        width, height = size
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            return width, height
        return None

    @staticmethod
    def _fallback_screen_size_provider() -> Optional[Tuple[int, int]]:
        if tk is None:  # pragma: no cover - Tk not available
            return None
        try:
            root = tk.Tk()
            root.withdraw()
            size = (root.winfo_screenwidth(), root.winfo_screenheight())
            root.destroy()
            return size
        except Exception:  # pragma: no cover - GUI-less envs
            logger.debug("Failed to query fallback screen size via Tk", exc_info=True)
            return None


# Import placed at the bottom to avoid circular dependencies during runtime
from recorder_tab import Rekord, RekordAction  # noqa: E402  # isort:skip

