"""Floating overlay widget — shows mic status near the cursor."""
import math
import threading
import tkinter as tk
from tkinter import font as tkfont


class Overlay:
    """Always-on-top, borderless tkinter window for mic status feedback."""

    WIDTH = 200
    HEIGHT = 180
    BG = "#1a1a2e"
    FG = "#e0e0e0"
    ACCENT_RED = "#e63946"
    ACCENT_GREEN = "#2a9d8f"
    ACCENT_BLUE = "#457b9d"

    def __init__(self):
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._label: tk.Label | None = None
        self._sub: tk.Label | None = None
        self._circle_id: int | None = None
        self._pulse_angle = 0.0
        self._pulse_active = False
        self._fade_after_id: str | None = None
        self._visible = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _ensure_root(self):
        if self._root is not None:
            return
        self._root = tk.Tk()
        self._root.withdraw()  # hide until needed

    def get_root(self) -> "tk.Tk":
        """Ensure the shared Tk root exists and return it (main-thread only).

        Other main-thread UI (e.g. the settings window) parents Toplevels on
        this single root rather than spinning up a second tk.Tk.
        """
        self._ensure_root()
        return self._root

    # ------------------------------------------------------------------
    def _build(self):
        """Create the toplevel window and widgets (once)."""
        root = self._root
        # Toplevel overlay
        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.configure(bg=self.BG)
        self._win.geometry(f"{self.WIDTH}x{self.HEIGHT}+0+0")
        self._win.withdraw()

        # Canvas for pulsing circle
        self._canvas = tk.Canvas(
            self._win,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=self.BG,
            highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True)

        # circle placeholder
        cx, cy, r = self.WIDTH // 2, 55, 22
        self._circle_id = self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=self.ACCENT_RED,
            width=3,
        )

        # main status label
        self._label = tk.Label(
            self._canvas,
            text="",
            font=tkfont.Font(size=13, weight="bold"),
            bg=self.BG,
            fg=self.FG,
        )
        self._label.place(relx=0.5, y=95, anchor="center")

        # subtitle
        self._sub = tk.Label(
            self._canvas,
            text="",
            font=tkfont.Font(size=9),
            bg=self.BG,
            fg="#888",
            wraplength=self.WIDTH - 20,
            justify="center",
        )
        self._sub.place(relx=0.5, y=120, anchor="center")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def show(self, near_x: int | None = None, near_y: int | None = None):
        """Show the overlay, optionally near a screen coordinate."""
        self._ensure_root()
        if self._canvas is None:
            self._build()

        # position
        if near_x is not None and near_y is not None:
            x = near_x - self.WIDTH // 2
            y = near_y - self.HEIGHT - 30  # above cursor
        else:
            # screen center
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            x = (sw - self.WIDTH) // 2
            y = (sh - self.HEIGHT) // 2

        # clamp to screen
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = max(0, min(x, sw - self.WIDTH))
        y = max(0, min(y, sh - self.HEIGHT))

        self._win.geometry(f"+{x}+{y}")
        self._win.deiconify()
        self._visible = True

        # cancel any pending hide
        if self._fade_after_id:
            self._root.after_cancel(self._fade_after_id)
            self._fade_after_id = None

    def hide(self):
        """Hide overlay."""
        if self._win:
            self._win.withdraw()
        self._visible = False
        self._pulse_active = False

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
        """Show pulsing red circle + Listening."""
        self.show(near_x=x, near_y=y)
        self._set_circle_color(self.ACCENT_RED)
        self._label.config(text="\U0001F399  Listening...", fg=self.FG)
        self._sub.config(text="Speak now — click side button or pause to stop")
        self._start_pulse()

    def state_transcribing(self, x: int = 0, y: int = 0):
        """Show blue circle + Transcribing..."""
        self.show(near_x=x, near_y=y)
        self._stop_pulse()
        self._set_circle_color(self.ACCENT_BLUE)
        self._label.config(text="\u2699 Transcribing...", fg=self.FG)
        self._sub.config(text="Processing speech to text...")

    def state_pasting(self, preview: str = "", x: int = 0, y: int = 0):
        """Show green check + preview."""
        self.show(near_x=x, near_y=y)
        self._stop_pulse()
        self._set_circle_color(self.ACCENT_GREEN)
        self._label.config(text="\u2714 Pasted!", fg=self.ACCENT_GREEN)
        short = preview[:80] + ("..." if len(preview) > 80 else "")
        self._sub.config(text=short if short else "Text inserted")
        self.hide_after(2500)

    def state_error(self, msg: str, x: int = 0, y: int = 0):
        """Show error state."""
        self.show(near_x=x, near_y=y)
        self._stop_pulse()
        self._set_circle_color("#ff6b6b")
        self._label.config(text="\u26A0 Error", fg="#ff6b6b")
        self._sub.config(text=msg)
        self.hide_after(5000)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _set_circle_color(self, color: str):
        if self._circle_id:
            self._canvas.itemconfig(self._circle_id, outline=color)

    def _start_pulse(self):
        self._pulse_active = True
        self._pulse_angle = 0.0
        self._animate_pulse()

    def _stop_pulse(self):
        self._pulse_active = False

    def _animate_pulse(self):
        if not self._pulse_active or not self._canvas:
            return
        self._pulse_angle += 0.12
        # Oscillate width between 2 and 7
        width = 3 + 3.5 * (1 + math.sin(self._pulse_angle))
        if self._circle_id:
            self._canvas.itemconfig(self._circle_id, width=int(width))
        self._root.after(40, self._animate_pulse)

    def run_one_tick(self):
        """Process one tk event — call from main loop."""
        self._ensure_root()
        try:
            self._root.update_idletasks()
            self._root.update()
        except tk.TclError:
            pass

    def destroy(self):
        """Clean exit."""
        self._pulse_active = False
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
