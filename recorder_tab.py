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

from dataclasses import dataclass, field
from datetime import datetime
import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

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
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None

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
        self._screen_width: Optional[int] = None
        self._screen_height: Optional[int] = None

    # pylint: disable=too-many-branches
    def start(
        self,
        name: Optional[str] = None,
        screen_size: Optional[Tuple[int, int]] = None,
    ) -> Optional[Rekord]:
        if self.is_recording:
            logger.warning("Recording is already active")
            return self.current_rekord

        if mouse is None or keyboard is None:
            logger.warning("pynput is required for recording; start() ignored")
            return None

        name = name or datetime.utcnow().strftime("Запись %Y-%m-%d %H:%M:%S")
        if screen_size is not None:
            self._screen_width, self._screen_height = screen_size
        else:
            self._screen_width = None
            self._screen_height = None
        self.current_rekord = Rekord(
            name=name,
            screen_width=self._screen_width,
            screen_height=self._screen_height,
        )
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

        for attr in ("_mouse_listener", "_keyboard_listener"):
            listener = getattr(self, attr)
            if listener is not None:
                listener.stop()
                try:
                    listener.join(timeout=1)
                except Exception:  # pragma: no cover - defensive logging
                    logger.debug("Listener join failed for %s", attr, exc_info=True)
                setattr(self, attr, None)

        if self._clipboard_monitor is not None:
            self._clipboard_monitor.stop()
            self._clipboard_monitor.join(timeout=1)
            self._clipboard_monitor = None

        rekord = self.current_rekord
        self.current_rekord = None
        self._screen_width = None
        self._screen_height = None
        return rekord

    # Event handlers -----------------------------------------------------
    def _on_mouse_move(self, x: int, y: int) -> None:
        if self.current_rekord:
            payload = self._with_coordinates({"x": x, "y": y})
            self.current_rekord.add_action("mouse_move", payload)

    def _on_mouse_click(self, x: int, y: int, button, pressed: bool) -> None:  # pragma: no cover
        if self.current_rekord:
            payload = {"x": x, "y": y, "button": str(button).split(".")[-1], "pressed": pressed}
            payload = self._with_coordinates(payload)
            self.current_rekord.add_action("mouse_click", payload)

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:  # pragma: no cover
        if self.current_rekord:
            payload = self._with_coordinates({"x": x, "y": y, "dx": dx, "dy": dy})
            self.current_rekord.add_action("mouse_scroll", payload)

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

    def _with_coordinates(self, payload: Dict[str, object]) -> Dict[str, object]:
        """Attach normalised coordinates when screen dimensions are known."""

        x = payload.get("x")
        y = payload.get("y")
        if (
            isinstance(x, (int, float))
            and isinstance(self._screen_width, int)
            and self._screen_width > 0
        ):
            payload["nx"] = float(x) / float(self._screen_width)
        if (
            isinstance(y, (int, float))
            and isinstance(self._screen_height, int)
            and self._screen_height > 0
        ):
            payload["ny"] = float(y) / float(self._screen_height)
        return payload


class RecorderTab(ttk.Frame):
    """Graphical tab containing start/stop buttons and a summary list."""

    def __init__(self, master: tk.Misc, on_record_ready: Callable[[Rekord], None]) -> None:
        super().__init__(master)
        self._on_record_ready = on_record_ready
        self._recorder = Recorder()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        self.status_var = tk.StringVar(value="Ожидание начала записи")
        self.name_var = tk.StringVar()

        header = ttk.Label(self, text="Запись действий пользователя", font=("TkDefaultFont", 12, "bold"))
        header.grid(column=0, row=0, sticky="w", padx=10, pady=(10, 4))

        name_row = ttk.Frame(self)
        name_row.grid(column=0, row=1, sticky="ew", padx=10)
        name_label = ttk.Label(name_row, text="Название записи:")
        name_label.grid(column=0, row=0, sticky="w")
        name_entry = ttk.Entry(name_row, textvariable=self.name_var)
        name_entry.grid(column=1, row=0, sticky="ew", padx=(6, 0))
        name_row.columnconfigure(1, weight=1)

        controls = ttk.Frame(self)
        controls.grid(column=0, row=2, sticky="ew", padx=10, pady=(6, 0))

        start_button = ttk.Button(controls, text="Начать запись", command=self._start_recording)
        start_button.grid(column=0, row=0, padx=(0, 5))

        stop_button = ttk.Button(controls, text="Остановить", command=self._stop_recording)
        stop_button.grid(column=1, row=0, padx=(5, 0))

        status_label = ttk.Label(self, textvariable=self.status_var)
        status_label.grid(column=0, row=3, sticky="ew", padx=10, pady=(10, 4))

        self.actions_list = tk.Listbox(self, height=10)
        self.actions_list.grid(column=0, row=4, sticky="nsew", padx=10, pady=(0, 10))

    def _start_recording(self) -> None:
        requested_name = self.name_var.get().strip() or None
        screen_size = (self.winfo_screenwidth(), self.winfo_screenheight())
        rekord = self._recorder.start(name=requested_name, screen_size=screen_size)
        if rekord is None:
            self.status_var.set("Невозможно начать запись: нет доступа к устройствам")
            return
        self.name_var.set(rekord.name)
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
            self._render_actions(rekord)
            self._on_record_ready(rekord)
        else:
            self.actions_list.delete(0, tk.END)
        self.name_var.set("")

    def _refresh_actions(self) -> None:
        if not self._recorder.is_recording or not self._recorder.current_rekord:
            return
        rekord = self._recorder.current_rekord
        self._render_actions(rekord)
        self.after(500, self._refresh_actions)

    def _render_actions(self, rekord: Rekord) -> None:
        self.actions_list.delete(0, tk.END)
        for action in rekord.actions[-50:]:
            human = f"{time.strftime('%H:%M:%S', time.localtime(action.timestamp))} · {action.event_type}"
            self.actions_list.insert(tk.END, human)

