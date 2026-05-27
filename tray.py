"""System-tray icon for SpeakEasy — Pause/Resume listening and Quit.

Runs pystray's icon loop on a daemon thread. Menu actions fire on that thread
and call back into the app via the provided callbacks (which should just enqueue
commands onto the app's thread-safe queue — never touch tkinter directly here).
"""
import threading
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

try:
    from crash_logger import log_event
except Exception:  # pragma: no cover
    def log_event(*_args, **_kwargs):
        pass


def _make_icon_image(paused: bool) -> Image.Image:
    """Draw a simple mic icon. Greyed when paused, red when listening."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=(30, 20, 50, 255))
    body = (120, 120, 120, 255) if paused else (210, 60, 70, 255)
    cx, cy = size // 2, size // 2 - 2
    draw.rounded_rectangle([cx - 9, cy - 17, cx + 9, cy + 9], radius=9, fill=body)
    draw.rectangle([cx - 2, cy + 9, cx + 2, cy + 17], fill=body)
    draw.rectangle([cx - 8, cy + 16, cx + 8, cy + 20], fill=body)
    return img


class Tray:
    """Tray icon wrapper. `is_paused` is a callable returning the live paused state."""

    def __init__(
        self,
        on_toggle_pause: Callable[[], None],
        on_quit: Callable[[], None],
        is_paused: Callable[[], bool],
        on_settings: Callable[[], None] | None = None,
    ):
        self._on_toggle_pause = on_toggle_pause
        self._on_quit = on_quit
        self._is_paused = is_paused
        self._on_settings = on_settings
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    def _menu(self) -> pystray.Menu:
        items = [
            pystray.MenuItem(
                lambda _item: "Resume listening" if self._is_paused() else "Pause listening",
                self._handle_pause,
            ),
        ]
        if self._on_settings is not None:
            items.append(pystray.MenuItem("Settings", self._handle_settings))
        items.append(pystray.MenuItem("Quit SpeakEasy", self._handle_quit))
        return pystray.Menu(*items)

    def _handle_settings(self, icon, _item) -> None:
        # Enqueue only — the settings window is tkinter and must open on the
        # app's main thread, not this pystray thread.
        if self._on_settings is not None:
            self._on_settings()

    def _handle_pause(self, icon, _item) -> None:
        # Just enqueue the request. The main thread flips the flag and then calls
        # refresh() — doing it here (on the pystray thread) would read the flag
        # before it has been updated and show stale state.
        self._on_toggle_pause()

    def _handle_quit(self, icon, _item) -> None:
        log_event("state", "tray quit selected")
        self._on_quit()       # ask the app to shut down cleanly
        icon.stop()           # stop the tray loop

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._icon = pystray.Icon(
            "SpeakEasy",
            _make_icon_image(self._is_paused()),
            "SpeakEasy — listening",
            menu=self._menu(),
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        log_event("state", "tray started")

    def refresh(self) -> None:
        """Update icon image + tooltip to reflect the current paused state."""
        if not self._icon:
            return
        paused = self._is_paused()
        self._icon.icon = _make_icon_image(paused)
        self._icon.title = "SpeakEasy — paused" if paused else "SpeakEasy — listening"
        self._icon.update_menu()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
