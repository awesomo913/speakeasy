"""Small tkinter settings window for SpeakEasy.

Opened from the tray's "Settings" item. tkinter is main-thread-only, so this is
always invoked on the app's main loop (the tray callback enqueues a command;
main.py calls ``open_settings_window`` while pumping the Tk root) — never
directly from the pystray thread.

Built as a Toplevel on the app's existing root (Overlay owns the single tk.Tk),
so we don't create a second Tk instance.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

import settings as _settings

try:
    from crash_logger import log_event
except Exception:  # pragma: no cover
    def log_event(*_args, **_kwargs):
        pass


# Palette matches the overlay so the app feels consistent.
_BG = "#1a1a2e"
_FG = "#e0e0e0"
_MUTED = "#8a8a9a"
_ACCENT = "#2a9d8f"
_RED = "#e63946"

# Single live window — reopening just raises the existing one.
_win: tk.Toplevel | None = None


def open_settings_window(root: tk.Tk) -> None:
    """Open (or raise) the settings window. Must run on the main thread."""
    global _win
    if _win is not None:
        try:
            if _win.winfo_exists():
                _win.deiconify()
                _win.lift()
                _win.focus_force()
                return
        except tk.TclError:
            pass
        _win = None

    win = tk.Toplevel(root)
    _win = win
    win.title("SpeakEasy Settings")
    win.configure(bg=_BG)
    win.resizable(False, False)
    win.geometry("360x210")
    win.attributes("-topmost", True)

    # Header: app name + mic glyph.
    header = tk.Label(
        win, text="\U0001F399  SpeakEasy",
        font=tkfont.Font(size=15, weight="bold"),
        bg=_BG, fg=_RED,
    )
    header.pack(anchor="w", padx=18, pady=(16, 12))

    # Autostart checkbox — ground truth from the Startup shortcut itself.
    autostart_var = tk.BooleanVar(value=_settings.is_autostart_enabled())
    status_var = tk.StringVar()

    def _refresh_status() -> None:
        status_var.set(
            "Autostart: ON — launches at login"
            if autostart_var.get() else
            "Autostart: off"
        )

    def _on_toggle() -> None:
        want = autostart_var.get()
        ok = _settings.set_autostart(want)
        if not ok:
            # Revert the checkbox to reality so the UI never lies.
            autostart_var.set(_settings.is_autostart_enabled())
            status_var.set("Couldn't change autostart — see logs")
        else:
            _refresh_status()

    chk = tk.Checkbutton(
        win,
        text="Start SpeakEasy when Windows starts",
        variable=autostart_var,
        command=_on_toggle,
        bg=_BG, fg=_FG,
        selectcolor=_BG,
        activebackground=_BG, activeforeground=_FG,
        font=tkfont.Font(size=10),
        anchor="w",
    )
    chk.pack(anchor="w", padx=18)

    status = tk.Label(
        win, textvariable=status_var,
        font=tkfont.Font(size=9),
        bg=_BG, fg=_MUTED, anchor="w",
    )
    status.pack(anchor="w", padx=40, pady=(2, 0))
    _refresh_status()

    # Close button, bottom-right.
    btn = tk.Button(
        win, text="Close", command=win.destroy,
        bg=_ACCENT, fg="#ffffff", relief="flat",
        activebackground="#23867a", activeforeground="#ffffff",
        font=tkfont.Font(size=10, weight="bold"),
        width=10, cursor="hand2",
    )
    btn.pack(side="bottom", anchor="e", padx=18, pady=16)

    def _on_close() -> None:
        global _win
        _win = None
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)
    log_event("state", "settings window opened")
