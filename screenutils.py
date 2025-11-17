"""Cross-platform helpers for querying the current screen dimensions."""

import logging
import sys
from typing import Optional, Tuple

try:  # pragma: no cover - Tk may be unavailable
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None

logger = logging.getLogger(__name__)


def detect_screen_size() -> Optional[Tuple[int, int]]:
    """Return the width/height of the primary display when possible."""

    size = _windows_screen_size()
    if size:
        return size

    size = _tk_screen_size()
    if size:
        return size

    return None


def _windows_screen_size() -> Optional[Tuple[int, int]]:
    if not sys.platform.startswith("win"):
        return None
    try:  # pragma: no cover - only executed on Windows
        import ctypes

        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
        if width > 0 and height > 0:
            return width, height
    except Exception:  # pragma: no cover - defensive logging
        logger.debug("Failed to read screen size via WinAPI", exc_info=True)
    return None


def _tk_screen_size() -> Optional[Tuple[int, int]]:
    if tk is None:
        return None
    try:  # pragma: no cover - GUI-less envs
        root = tk.Tk()
        root.withdraw()
        size = (int(root.winfo_screenwidth()), int(root.winfo_screenheight()))
        root.destroy()
        if size[0] > 0 and size[1] > 0:
            return size
    except Exception:
        logger.debug("Failed to query Tk screen size", exc_info=True)
    return None
