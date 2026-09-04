"""Persistent taskbar-corner status dot — always visible, unlike the
cursor-following overlay (which only appears during an action and hides).

Shares the same Tk root as Overlay (no second interpreter/process — the RAM
cost is one more tiny canvas ticking on the mainloop that's already running).
"""
from __future__ import annotations

import ctypes
import math
import tkinter as tk
from collections.abc import Callable
from ctypes import wintypes

try:
    from crash_logger import log_event
except Exception:  # pragma: no cover
    def log_event(*_args, **_kwargs):
        pass

try:
    import settings
except Exception:  # pragma: no cover — dev-standalone import fallback
    settings = None

# Colors match overlay.py exactly so the two indicators never disagree.
COLOR_IDLE = "#2a9d8f"      # green — armed, ready
COLOR_RECORDING = "#e63946"  # red
COLOR_TRANSCRIBING = "#457b9d"  # blue
COLOR_PASTING = "#4fd1b8"    # bright green flash
COLOR_PAUSED = "#5a5a5a"     # grey
COLOR_ERROR = "#ff6b6b"

SIZE = 16
MARGIN = 8
TRANSPARENT_KEY = "#123456"  # magic color-key made transparent via wm_attributes
_DRAG_THRESHOLD = 4  # px of movement before a press counts as a drag, not a click

SPI_GETWORKAREA = 0x0030


def _work_area() -> tuple[int, int, int, int]:
    """Screen area excluding the taskbar (left, top, right, bottom)."""
    rect = wintypes.RECT()
    try:
        ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        return 0, 0, 1920, 1080


class StatusDot:
    """Small always-on-top dot showing SpeakEasy's live state.

    Left-click (no drag) toggles pause/resume. Drag repositions it (position
    persists). Right-click opens a tiny Settings/Quit menu.
    """

    def __init__(
        self,
        root: "tk.Tk",
        on_toggle_pause: Callable[[], None],
        on_settings: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ):
        self._root = root
        self._on_toggle_pause = on_toggle_pause
        self._on_settings = on_settings
        self._on_quit = on_quit

        self._win: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._circle_id: int | None = None
        self._pulse_active = False
        self._pulse_angle = 0.0
        self._pulse_color = COLOR_IDLE

        self._drag_start_x = 0
        self._drag_start_y = 0
        self._win_start_x = 0
        self._win_start_y = 0
        self._dragged = False

        # Remembers the last non-error state so a flash can revert to it.
        self._base_color = COLOR_IDLE

    # ------------------------------------------------------------------
    def _default_position(self) -> tuple[int, int]:
        left, top, right, bottom = _work_area()
        return right - SIZE - MARGIN, bottom - SIZE - MARGIN

    def _load_position(self) -> tuple[int, int]:
        if settings is not None:
            try:
                data = settings.load()
                x, y = data.get("dot_x"), data.get("dot_y")
                if isinstance(x, int) and isinstance(y, int):
                    return x, y
            except Exception:  # noqa: BLE001 — never block startup on a bad prefs file
                pass
        return self._default_position()

    def _save_position(self, x: int, y: int) -> None:
        if settings is None:
            return
        try:
            data = settings.load()
            data["dot_x"] = x
            data["dot_y"] = y
            settings.save(data)
        except Exception as exc:  # noqa: BLE001 — position persistence is best-effort
            log_event("warning", "status dot position save failed", {"error": str(exc)})

    # ------------------------------------------------------------------
    def _build(self) -> None:
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass  # some Windows configs reject color-keying; solid bg is fine
        win.configure(bg=TRANSPARENT_KEY)

        x, y = self._load_position()
        win.geometry(f"{SIZE}x{SIZE}+{x}+{y}")

        canvas = tk.Canvas(win, width=SIZE, height=SIZE, bg=TRANSPARENT_KEY, highlightthickness=0)
        canvas.pack()
        pad = 2
        circle_id = canvas.create_oval(pad, pad, SIZE - pad, SIZE - pad, fill=COLOR_IDLE, outline="")

        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        canvas.bind("<Button-3>", self._on_right_click)

        self._win = win
        self._canvas = canvas
        self._circle_id = circle_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def show(self) -> None:
        if self._win is None:
            self._build()

    def destroy(self) -> None:
        self._pulse_active = False
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None

    def set_state(self, state, paused: bool) -> None:
        """Reflect main.py's State enum + paused flag as a color/pulse."""
        from main import State  # local import — avoids a circular import at module load

        if paused:
            self._set(COLOR_PAUSED, pulse=False)
        elif state == State.RECORDING:
            self._set(COLOR_RECORDING, pulse=True)
        elif state == State.TRANSCRIBING:
            self._set(COLOR_TRANSCRIBING, pulse=True)
        elif state == State.PASTING:
            self._set(COLOR_PASTING, pulse=False)
        else:  # IDLE
            self._set(COLOR_IDLE, pulse=False)

    def flash_error(self, revert_state, paused: bool, duration_ms: int = 600) -> None:
        """Briefly show red, then restore whatever set_state would show now."""
        self._set(COLOR_ERROR, pulse=False)
        self._root.after(duration_ms, lambda: self.set_state(revert_state, paused))

    # ------------------------------------------------------------------
    # Drag / click / menu
    # ------------------------------------------------------------------
    def _on_press(self, event) -> None:
        if self._win is None:
            return
        self._dragged = False
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._win_start_x = self._win.winfo_x()
        self._win_start_y = self._win.winfo_y()

    def _on_drag(self, event) -> None:
        if self._win is None:
            return
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        if abs(dx) > _DRAG_THRESHOLD or abs(dy) > _DRAG_THRESHOLD:
            self._dragged = True
        if self._dragged:
            self._win.geometry(f"+{self._win_start_x + dx}+{self._win_start_y + dy}")

    def _on_release(self, _event) -> None:
        if self._win is None:
            return
        if self._dragged:
            self._save_position(self._win.winfo_x(), self._win.winfo_y())
        else:
            self._on_toggle_pause()

    def _on_right_click(self, event) -> None:
        menu = tk.Menu(self._win, tearoff=0)
        if self._on_settings is not None:
            menu.add_command(label="Settings", command=self._on_settings)
        if self._on_quit is not None:
            menu.add_command(label="Quit SpeakEasy", command=self._on_quit)
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _set(self, color: str, pulse: bool) -> None:
        self._base_color = color
        if self._canvas is None or self._circle_id is None:
            return
        self._canvas.itemconfig(self._circle_id, fill=color)
        if pulse:
            self._start_pulse(color)
        else:
            self._pulse_active = False
            pad = 2
            self._canvas.coords(self._circle_id, pad, pad, SIZE - pad, SIZE - pad)

    def _start_pulse(self, color: str) -> None:
        self._pulse_active = True
        self._pulse_angle = 0.0
        self._pulse_color = color
        self._animate_pulse()

    def _animate_pulse(self) -> None:
        if not self._pulse_active or self._canvas is None:
            return
        self._pulse_angle += 0.15
        pad = 1.5 + 1.5 * (1 + math.sin(self._pulse_angle))
        self._canvas.coords(self._circle_id, pad, pad, SIZE - pad, SIZE - pad)
        self._root.after(40, self._animate_pulse)
