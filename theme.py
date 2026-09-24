"""Shared color palette + font used by every tkinter surface in SpeakEasy.

Keeping this in one module means overlay.py, status_dot.py, tray.py, and
settings_window.py can never drift into different shades of "dark UI."
"""
from __future__ import annotations

# ── Palette ──────────────────────────────────────────────────────────
BG = "#14141f"          # window background
SURFACE = "#1e1e2e"     # cards / panels / entries
TEXT = "#e6e6f0"        # primary text
MUTED = "#8a8aa3"       # secondary / help text
ACCENT = "#2ec4b6"      # teal — ready / idle / primary actions
RECORDING = "#ef476f"   # red — actively recording
TRANSCRIBING = "#4d96ff"  # blue — processing
PAUSED = "#5a5a6e"      # grey — paused / disabled

# Convenience aliases used by state-driven UI (overlay, status dot).
COLOR_IDLE = ACCENT
COLOR_RECORDING = RECORDING
COLOR_TRANSCRIBING = TRANSCRIBING
COLOR_PASTING = ACCENT
COLOR_PAUSED = PAUSED
COLOR_ERROR = "#ff6b6b"

FONT_FAMILY = "Segoe UI"


def font(size: int, weight: str = "normal"):
    """Return a (family, size, weight) tuple tkinter accepts directly.

    Using the tuple form (rather than tkinter.font.Font) means callers don't
    need a Tk root to exist yet when building this — handy for constants.
    """
    if weight == "normal":
        return (FONT_FAMILY, size)
    return (FONT_FAMILY, size, weight)
