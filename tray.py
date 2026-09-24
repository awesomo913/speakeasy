"""System-tray icon for SpeakEasy — Pause/Resume listening and Quit.

Runs pystray's icon loop on a daemon thread. Menu actions fire on that thread
and call back into the app via the provided callbacks (which should just enqueue
commands onto the app's thread-safe queue — never touch tkinter directly here).
"""
from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable

import pystray
from PIL import Image

from icon_art import PAUSED_BOTTOM, PAUSED_TOP, build_icon, build_icon_with_badge
from speakeasy_log import default_log_dir, log_event
from theme import ACCENT, RECORDING, TRANSCRIBING
from version import __version__

_ICON_RENDER_SIZE = 256  # drawn big, downscaled for anti-aliased tray edges
_ICON_DISPLAY_SIZE = 64


def _make_icon_image(paused: bool, recording: bool = False) -> Image.Image:
    """Shared gradient mic tile. Grey gradient when paused, red badge when recording."""
    if recording:
        img = build_icon_with_badge(ACCENT, TRANSCRIBING, RECORDING, _ICON_RENDER_SIZE)
    elif paused:
        img = build_icon(PAUSED_TOP, PAUSED_BOTTOM, _ICON_RENDER_SIZE)
    else:
        img = build_icon(ACCENT, TRANSCRIBING, _ICON_RENDER_SIZE)
    return img.resize((_ICON_DISPLAY_SIZE, _ICON_DISPLAY_SIZE), Image.LANCZOS)


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
            pystray.MenuItem(f"SpeakEasy v{__version__}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _item: "Resume listening" if self._is_paused() else "Pause listening",
                self._handle_pause,
            ),
        ]
        if self._on_settings is not None:
            items.append(pystray.MenuItem("Settings…", self._handle_settings))
        items.append(pystray.MenuItem("Open log folder", self._handle_open_logs))
        items.append(pystray.Menu.SEPARATOR)
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

    def _handle_open_logs(self, icon, _item) -> None:
        log_dir = default_log_dir()
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["explorer", str(log_dir)])  # noqa: S603, S607
        except OSError as exc:
            log_event("failure", "open log folder failed",
                      {"error": str(exc), "path": str(log_dir)})

    def _handle_quit(self, icon, _item) -> None:
        log_event("state", "tray quit selected")
        self._on_quit()       # ask the app to shut down cleanly
        icon.stop()           # stop the tray loop

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._icon = pystray.Icon(
            "SpeakEasy",
            _make_icon_image(self._is_paused()),
            f"SpeakEasy v{__version__} — listening",
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
        self._icon.title = (
            f"SpeakEasy v{__version__} — paused" if paused
            else f"SpeakEasy v{__version__} — listening"
        )
        self._icon.update_menu()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
