"""Graphical interface for the desktop task automation application."""

import logging
import queue
from typing import Optional

import tkinter as tk
from tkinter import ttk

from automation import AutomationManager
from recorder_tab import Rekord, RecorderTab


class TkQueueHandler(logging.Handler):
    """Forward log entries into a queue that the Tk loop can consume."""

    def __init__(self, target_queue: "queue.Queue[str]") -> None:
        super().__init__()
        self.target_queue = target_queue

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.target_queue.put(message)


class LogTab(ttk.Frame):
    """First tab: human friendly view of the application logs."""

    def __init__(self, master: tk.Misc, log_queue: "queue.Queue[str]") -> None:
        super().__init__(master)
        self.log_queue = log_queue

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.text = tk.Text(self, state="disabled", wrap="word", height=20)
        self.text.grid(column=0, row=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(self, command=self.text.yview)
        scrollbar.grid(column=1, row=0, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.after(200, self._poll_log_queue)

    def _poll_log_queue(self) -> None:
        updated = False
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.text.configure(state="normal")
            self.text.insert(tk.END, message + "\n")
            self.text.configure(state="disabled")
            self.text.see(tk.END)
            updated = True
        if updated:
            self.update_idletasks()
        self.after(300, self._poll_log_queue)


class AutomationTab(ttk.Frame):
    """Second tab: playback controls for saved records."""

    def __init__(self, master: tk.Misc, manager: AutomationManager) -> None:
        super().__init__(master)
        self.manager = manager
        self.selected_index: Optional[int] = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Label(self, text="Воспроизведение сценариев", font=("TkDefaultFont", 12, "bold"))
        header.grid(column=0, row=0, sticky="w", padx=10, pady=(10, 4))

        self.records_list = tk.Listbox(self, height=12)
        self.records_list.grid(column=0, row=1, sticky="nsew", padx=10)
        self.records_list.bind("<<ListboxSelect>>", self._on_select)

        controls = ttk.Frame(self)
        controls.grid(column=0, row=2, sticky="ew", padx=10, pady=(8, 10))

        play_button = ttk.Button(controls, text="▶ Воспроизвести", command=self._play_selected)
        play_button.grid(column=0, row=0, padx=(0, 5))

        stop_button = ttk.Button(controls, text="⏹ Остановить", command=self.manager.stop_playback)
        stop_button.grid(column=1, row=0, padx=(5, 5))

        clear_button = ttk.Button(controls, text="🗑 Очистить", command=self._clear_records)
        clear_button.grid(column=2, row=0, padx=(5, 0))

    def refresh(self) -> None:
        self.records_list.delete(0, tk.END)
        for rekord in self.manager.records:
            summary = rekord.to_summary()
            self.records_list.insert(tk.END, summary)
        self.selected_index = None

    def _on_select(self, event) -> None:  # pragma: no cover - bound to GUI event
        selection = self.records_list.curselection()
        self.selected_index = selection[0] if selection else None

    def _play_selected(self) -> None:
        if self.selected_index is None:
            return
        rekord = self.manager.records[self.selected_index]
        self.manager.playback(rekord)

    def _clear_records(self) -> None:
        self.manager.clear()
        self.refresh()

class AutomationApp(tk.Tk):
    """Main application window that hosts all three tabs."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Автоматизация рабочих процессов")
        self.geometry("960x640")

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self._setup_logging()

        self.manager = AutomationManager()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.log_tab = LogTab(notebook, self.log_queue)
        notebook.add(self.log_tab, text="Журнал")

        self.automation_tab = AutomationTab(notebook, self.manager)
        notebook.add(self.automation_tab, text="Автоматизация")
        self.automation_tab.refresh()

        recorder_tab = RecorderTab(notebook, on_record_ready=self._on_record_ready)
        notebook.add(recorder_tab, text="Запись")

    def _setup_logging(self) -> None:
        handler = TkQueueHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s — %(message)s", "%H:%M:%S"))
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)

    def _on_record_ready(self, rekord: Rekord) -> None:
        logging.info("Получена запись: %s (%d действий)", rekord.name, len(rekord.actions))
        self.manager.add_record(rekord)
        self.automation_tab.refresh()


def run_app() -> None:
    """Entry point used by the ``__main__`` block and external callers."""

    app = AutomationApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()

