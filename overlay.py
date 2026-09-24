"""Floating pill-shaped overlay — shows mic status near the cursor.

Small (~220x64), rounded, dark, and always clamped on-screen. Uses the same
transparent-color-key trick as status_dot.py to get real rounded corners
instead of a rectangular tkinter window.
"""
from __future__ import annotations

import math
import threading
import tkinter as tk

from speakeasy_log import log_event
from theme import (
    ACCENT,
    COLOR_ERROR,
    FONT_FAMILY,
    MUTED,
    PAUSED,
    RECORDING,
    SURFACE,
    TEXT,
    TRANSCRIBING,
)

TRANSPARENT_KEY = "#0a0a12"  # magic color-key made transparent via wm_attributes

_MAX_SUB_CHARS = 34  # keeps the subtitle to one line at the pill's width
_MAX_PREVIEW_CHARS = 40  # pasted-text preview, per spec: ~40 chars + an ellipsis


def _truncate(text: str, limit: int) -> str:
    """One-line-safe truncation: cut to limit and end with an ellipsis."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


class Overlay:
    """Always-on-top, borderless tkinter pill for mic status feedback."""

    WIDTH = 300
    HEIGHT = 78
    RADIUS = 24

    def __init__(self):
        self._root: tk.Tk | None = None
        self._win: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._pill_id: int | None = None
        self._dot_id: int | None = None
        self._check_id: int | None = None
        self._label: tk.Label | None = None
        self._sub: tk.Label | None = None
        self._pulse_angle = 0.0
        self._pulse_active = False
        self._spin_active = False
        self._spin_angle = 0.0
        self._fade_after_id: str | None = None
        self._visible = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _ensure_root(self):
        if self._root is not None:
            return
        self._root = tk.Tk()
        self._root.withdraw()  # hide until needed

    def get_root(self) -> tk.Tk:
        """Ensure the shared Tk root exists and return it (main-thread only).

        Other main-thread UI (e.g. the settings window) parents Toplevels on
        this single root rather than spinning up a second tk.Tk.
        """
        self._ensure_root()
        return self._root

    # ------------------------------------------------------------------
    def _rounded_pill(self, canvas: tk.Canvas, color: str) -> int:
        """Draw (or return the id of) a rounded rectangle filling the canvas."""
        w, h, r = self.WIDTH, self.HEIGHT, self.RADIUS
        points = [
            r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h,
            w - r, h, r, h, 0, h, 0, h - r, 0, r, 0, 0,
        ]
        return canvas.create_polygon(points, smooth=True, fill=color, outline=color)

    def _build(self):
        """Create the toplevel window and widgets (once)."""
        root = self._root
        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        try:
            self._win.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError as exc:
            log_event("warning", "overlay transparentcolor unsupported", {"error": str(exc)})
        self._win.configure(bg=TRANSPARENT_KEY)
        self._win.geometry(f"{self.WIDTH}x{self.HEIGHT}+0+0")
        self._win.withdraw()

        self._canvas = tk.Canvas(
            self._win,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True)
        self._pill_id = self._rounded_pill(self._canvas, SURFACE)

        # status indicator (small circle on the left, vertically centered)
        cx, cy, r = 26, self.HEIGHT // 2, 7
        self._dot_id = self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r, fill=RECORDING, outline="",
        )
        # checkmark drawn on top of the dot for the "pasted" state only —
        # hidden the rest of the time via canvas item state, not recreated.
        self._check_id = self._canvas.create_line(
            cx - 3, cy, cx - 1, cy + 3, cx + 3.5, cy - 3.5,
            fill="#ffffff", width=2, capstyle="round", joinstyle="round",
            state="hidden",
        )

        # Title + subtitle are vertically centered as a block, one line each
        # (the subtitle is truncated in code, never wrapped, so it can never
        # get clipped by the pill's fixed height).
        # Both labels live in one frame that is centered vertically; they size
        # to their font's real line height, so descenders never clip at any DPI.
        text_w = self.WIDTH - 60
        block = tk.Frame(self._canvas, bg=SURFACE)
        block.place(x=48, rely=0.5, anchor="w", width=text_w)
        self._label = tk.Label(
            block,
            text="",
            font=(FONT_FAMILY, 12, "bold"),
            bg=SURFACE,
            fg=TEXT,
            anchor="w",
            pady=0,
        )
        self._label.pack(fill="x")

        self._sub = tk.Label(
            block,
            text="",
            font=(FONT_FAMILY, 9),
            bg=SURFACE,
            fg=MUTED,
            anchor="w",
            justify="left",
            pady=0,
        )
        self._sub.pack(fill="x")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def show(self, near_x: int | None = None, near_y: int | None = None):
        """Show the overlay, optionally near a screen coordinate."""
        self._ensure_root()
        if self._canvas is None:
            self._build()

        if near_x is not None and near_y is not None:
            x = near_x - self.WIDTH // 2
            y = near_y - self.HEIGHT - 24  # above cursor
        else:
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            x = (sw - self.WIDTH) // 2
            y = (sh - self.HEIGHT) // 2

        # clamp so the pill is always fully on-screen
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = max(0, min(x, sw - self.WIDTH))
        y = max(0, min(y, sh - self.HEIGHT))

        self._win.geometry(f"+{x}+{y}")
        self._win.deiconify()
        self._visible = True

        if self._fade_after_id:
            self._root.after_cancel(self._fade_after_id)
            self._fade_after_id = None

    def hide(self):
        """Hide overlay."""
        if self._win:
            self._win.withdraw()
        self._visible = False
        self._pulse_active = False
        self._spin_active = False

    def hide_after(self, delay_ms: int = 2500):
        """Schedule auto-hide."""
        self._ensure_root()
        if self._fade_after_id:
            self._root.after_cancel(self._fade_after_id)
        self._fade_after_id = self._root.after(delay_ms, self.hide)

    # ------------------------------------------------------------------
    # States
    # ------------------------------------------------------------------
    def state_idle(self):
        """Show idle/ready state (practically hidden)."""
        self.hide()

    def state_recording(self, x: int = 0, y: int = 0):
        """Pulsing red dot + 'Listening...'."""
        self.show(near_x=x, near_y=y)
        self._stop_spin()
        self._hide_check()
        self._set_dot_color(RECORDING)
        self._label.config(text="Listening…", fg=TEXT)
        self._sub.config(text=_truncate("Speak now · trigger again to stop", _MAX_SUB_CHARS))
        self._start_pulse()

    def state_transcribing(self, x: int = 0, y: int = 0):
        """Spinning blue dot + 'Transcribing...'."""
        self.show(near_x=x, near_y=y)
        self._stop_pulse()
        self._hide_check()
        self._set_dot_color(TRANSCRIBING)
        self._label.config(text="Transcribing…", fg=TEXT)
        self._sub.config(text=_truncate("Turning speech into text", _MAX_SUB_CHARS))
        self._start_spin()

    def state_pasting(self, preview: str = "", x: int = 0, y: int = 0):
        """Teal dot + checkmark, and a short preview of what was pasted."""
        self.show(near_x=x, near_y=y)
        self._stop_pulse()
        self._stop_spin()
        self._set_dot_color(ACCENT)
        self._show_check()
        self._label.config(text="Pasted", fg=TEXT)
        short = _truncate(preview, _MAX_PREVIEW_CHARS) if preview else "Text inserted"
        self._sub.config(text=short)
        self.hide_after(2200)

    def state_error(self, msg: str, x: int = 0, y: int = 0):
        """Warning glyph + error message."""
        self.show(near_x=x, near_y=y)
        self._stop_pulse()
        self._stop_spin()
        self._hide_check()
        self._set_dot_color(COLOR_ERROR)
        self._label.config(text="⚠ Error", fg=COLOR_ERROR)
        self._sub.config(text=_truncate(msg, _MAX_SUB_CHARS))
        self.hide_after(4500)

    def state_paused(self, x: int = 0, y: int = 0):
        """Grey dot + 'Paused' (used when the tray toggles pause mid-flow)."""
        self.show(near_x=x, near_y=y)
        self._stop_pulse()
        self._stop_spin()
        self._hide_check()
        self._set_dot_color(PAUSED)
        self._label.config(text="Paused", fg=TEXT)
        self._sub.config(text="Listening is paused")
        self.hide_after(1500)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _set_dot_color(self, color: str):
        if self._dot_id is not None and self._canvas is not None:
            self._canvas.itemconfig(self._dot_id, fill=color)

    def _show_check(self):
        if self._check_id is not None and self._canvas is not None:
            self._canvas.itemconfig(self._check_id, state="normal")

    def _hide_check(self):
        if self._check_id is not None and self._canvas is not None:
            self._canvas.itemconfig(self._check_id, state="hidden")

    def _start_pulse(self):
        self._pulse_active = True
        self._pulse_angle = 0.0
        self._animate_pulse()

    def _stop_pulse(self):
        self._pulse_active = False

    def _animate_pulse(self):
        if not self._pulse_active or not self._canvas or self._dot_id is None:
            return
        self._pulse_angle += 0.15
        r = 5 + 3 * (1 + math.sin(self._pulse_angle))
        cx, cy = 26, self.HEIGHT // 2
        self._canvas.coords(self._dot_id, cx - r, cy - r, cx + r, cy + r)
        self._root.after(40, self._animate_pulse)

    def _start_spin(self):
        self._spin_active = True
        self._spin_angle = 0.0
        self._animate_spin()

    def _stop_spin(self):
        self._spin_active = False

    def _animate_spin(self):
        """Simple 'spinner' feel: oscillate the dot's opacity via radius."""
        if not self._spin_active or not self._canvas or self._dot_id is None:
            return
        self._spin_angle += 0.25
        r = 4 + 2.5 * (1 + math.sin(self._spin_angle))
        cx, cy = 26, self.HEIGHT // 2
        self._canvas.coords(self._dot_id, cx - r, cy - r, cx + r, cy + r)
        self._root.after(35, self._animate_spin)

    def run_one_tick(self):
        """Process one tk event — call from main loop."""
        self._ensure_root()
        try:
            self._root.update_idletasks()
            self._root.update()
        except tk.TclError as exc:
            log_event("warning", "overlay tick failed", {"error": str(exc)})

    def destroy(self):
        """Clean exit."""
        self._pulse_active = False
        self._spin_active = False
        if self._root:
            try:
                self._root.destroy()
            except tk.TclError as exc:
                log_event("warning", "overlay root destroy failed", {"error": str(exc)})
