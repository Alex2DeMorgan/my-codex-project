"""UI and recording logic for the recorder tab of the application.

The module exposes three main building blocks:

``Rekord``
    Dataclass that stores the list of actions captured during a recording
    session.  The specification explicitly mentioned using a class with this
    name, so we keep it here.

``Recorder``
    Service class responsible for talking to the OS and collecting keyboard,
    mouse and clipboard events.  It cooperates with ``pynput`` when available
    and falls back to a no-op mode otherwise.  The class emits log messages so
    the user can easily understand what is happening in the dedicated log tab.

``RecorderTab``
    A ``tkinter`` frame that can be inserted inside a ``ttk.Notebook``.  It
    exposes a simple user experience for starting/stopping recordings and
    signals the front-end whenever a new ``Rekord`` is ready through a callback
    provided by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

import tkinter as tk
from tkinter import ttk

try:  # pragma: no cover - optional dependency
    from pynput import keyboard, mouse
except Exception:  # pragma: no cover
    keyboard = None
    mouse = None

try:  # pragma: no cover - optional dependency
    import pyperclip
except Exception:  # pragma: no cover
    pyperclip = None


logger = logging.getLogger(__name__)


@dataclass
class RekordAction:
    """Low level action representation for a Rekord instance."""

    timestamp: float
    event_type: str
    payload: Dict[str, object]


@dataclass
class Rekord:
    """Container for a single recording session."""

    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    actions: List[RekordAction] = field(default_factory=list)

    def add_action(self, event_type: str, payload: Dict[str, object]) -> None:
        action = RekordAction(timestamp=time.time(), event_type=event_type, payload=payload)
        logger.debug("Recording %s event: %s", event_type, payload)
        self.actions.append(action)

    def to_summary(self) -> str:
        return f"{self.name} · {len(self.actions)} действий"


class ClipboardMonitor(threading.Thread):
    """Continuously monitor the clipboard when recording is active."""

    def __init__(self, callback: Callable[[str], None], poll_interval: float = 0.5) -> None:
        super().__init__(daemon=True)
        self._callback = callback
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._last_value: Optional[str] = None

    def run(self) -> None:  # pragma: no cover - thread based
        if pyperclip is None:
            logger.info("Clipboard monitoring disabled: pyperclip not installed")
            return

        while not self._stop_event.is_set():
            try:
                value = pyperclip.paste()
            except Exception:
                logger.exception("Failed to read clipboard contents")
                return
            if value != self._last_value:
                self._last_value = value
                logger.debug("Clipboard changed")
                self._callback(value)
            time.sleep(self._poll_interval)

    def stop(self) -> None:
        self._stop_event.set()


class Recorder:
    """Service that coordinates mouse/keyboard listeners and clipboard monitor."""

    def __init__(self) -> None:
        self.is_recording = False
        self.current_rekord: Optional[Rekord] = None
        self._mouse_listener = None
        self._keyboard_listener = None
        self._clipboard_monitor: Optional[ClipboardMonitor] = None

    # pylint: disable=too-many-branches
    def start(self, name: Optional[str] = None) -> Optional[Rekord]:
        if self.is_recording:
            logger.warning("Recording is already active")
            return self.current_rekord

        if mouse is None or keyboard is None:
            logger.warning("pynput is required for recording; start() ignored")
            return None

        name = name or datetime.utcnow().strftime("Запись %Y-%m-%d %H:%M:%S")
        self.current_rekord = Rekord(name=name)
        self.is_recording = True
        logger.info("Recording started: %s", self.current_rekord.name)

        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self._mouse_listener.start()

        self._keyboard_listener = keyboard.Listener(
            on_press=lambda key: self._on_keyboard(key, True),
            on_release=lambda key: self._on_keyboard(key, False),
        )
        self._keyboard_listener.start()

        self._clipboard_monitor = ClipboardMonitor(self._on_clipboard)
        self._clipboard_monitor.start()

        return self.current_rekord

    def stop(self) -> Optional[Rekord]:
        if not self.is_recording:
            logger.warning("Recorder.stop() called while not recording")
            return None

        logger.info("Recording stopped: %s", self.current_rekord.name if self.current_rekord else "–")
        self.is_recording = False

        for listener in (self._mouse_listener, self._keyboard_listener):
            if listener is not None:
                listener.stop()

        if self._clipboard_monitor is not None:
            self._clipboard_monitor.stop()

        rekord = self.current_rekord
        self.current_rekord = None
        return rekord

    # Event handlers -----------------------------------------------------
    def _on_mouse_move(self, x: int, y: int) -> None:
        if self.current_rekord:
            self.current_rekord.add_action("mouse_move", {"x": x, "y": y})

    def _on_mouse_click(self, x: int, y: int, button, pressed: bool) -> None:  # pragma: no cover
        if self.current_rekord:
            self.current_rekord.add_action(
                "mouse_click",
                {"x": x, "y": y, "button": str(button).split(".")[-1], "pressed": pressed},
            )

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:  # pragma: no cover
        if self.current_rekord:
            self.current_rekord.add_action(
                "mouse_scroll", {"x": x, "y": y, "dx": dx, "dy": dy}
            )

    def _on_keyboard(self, key, pressed: bool) -> None:  # pragma: no cover
        if self.current_rekord:
            try:
                name = key.char if hasattr(key, "char") and key.char else str(key)
            except AttributeError:
                name = str(key)
            self.current_rekord.add_action(
                "keyboard", {"key": name, "pressed": pressed}
            )

    def _on_clipboard(self, value: str) -> None:
        if self.current_rekord:
            self.current_rekord.add_action("clipboard", {"value": value})


class RecorderTab(ttk.Frame):
    """Graphical tab containing start/stop buttons and a summary list."""

    def __init__(self, master: tk.Misc, on_record_ready: Callable[[Rekord], None]) -> None:
        super().__init__(master)
        self._on_record_ready = on_record_ready
        self._recorder = Recorder()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.status_var = tk.StringVar(value="Ожидание начала записи")

        header = ttk.Label(self, text="Запись действий пользователя", font=("TkDefaultFont", 12, "bold"))
        header.grid(column=0, row=0, sticky="w", padx=10, pady=(10, 4))

        controls = ttk.Frame(self)
        controls.grid(column=0, row=1, sticky="ew", padx=10)

        start_button = ttk.Button(controls, text="Начать запись", command=self._start_recording)
        start_button.grid(column=0, row=0, padx=(0, 5))

        stop_button = ttk.Button(controls, text="Остановить", command=self._stop_recording)
        stop_button.grid(column=1, row=0, padx=(5, 0))

        status_label = ttk.Label(self, textvariable=self.status_var)
        status_label.grid(column=0, row=2, sticky="ew", padx=10, pady=(10, 4))

        self.actions_list = tk.Listbox(self, height=10)
        self.actions_list.grid(column=0, row=3, sticky="nsew", padx=10, pady=(0, 10))

    def _start_recording(self) -> None:
        rekord = self._recorder.start()
        if rekord is None:
            self.status_var.set("Невозможно начать запись: нет доступа к устройствам")
            return
        self.actions_list.delete(0, tk.END)
        self.status_var.set(f"Идёт запись: {rekord.name}")
        self.after(200, self._refresh_actions)

    def _stop_recording(self) -> None:
        rekord = self._recorder.stop()
        if rekord is None:
            self.status_var.set("Запись не активна")
            return
        self.status_var.set(f"Запись завершена: {rekord.to_summary()}")
        if rekord.actions:
            self._on_record_ready(rekord)

    def _refresh_actions(self) -> None:
        if not self._recorder.is_recording or not self._recorder.current_rekord:
            return
        rekord = self._recorder.current_rekord
        self.actions_list.delete(0, tk.END)
        for action in rekord.actions[-50:]:
            human = f"{time.strftime('%H:%M:%S', time.localtime(action.timestamp))} · {action.event_type}"
            self.actions_list.insert(tk.END, human)
        self.after(500, self._refresh_actions)

