"""Clipboard-based text insertion — saves old clipboard, copies new text, simulates Ctrl+V."""
from __future__ import annotations

import threading
import time

import pyperclip
from pynput.keyboard import Controller, Key

from speakeasy_log import log_event


class TextInserter:
    """Pastes transcribed text at the current cursor via clipboard + Ctrl+V."""

    def __init__(self, restore_delay_s: float = 0.3):
        self._keyboard = Controller()
        self._restore_delay_s = restore_delay_s

    def paste(self, text: str) -> str | None:
        """Paste the given text. Returns the previous clipboard content (or None)."""
        if not text:
            return None

        # 1. Save current clipboard
        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException as exc:
            log_event("warning", "reading previous clipboard failed", {"error": str(exc)})
            previous = ""

        # 2. Copy our text to clipboard. If this fails, the clipboard still
        # holds whatever it had before — simulating Ctrl+V now would paste
        # stale/unrelated content and look like a successful (but wrong)
        # paste, so we log and re-raise instead of guessing.
        try:
            pyperclip.copy(text)
        except pyperclip.PyperclipException as exc:
            log_event("failure", "copying transcript to clipboard failed",
                      {"error": str(exc)})
            raise
        time.sleep(0.05)

        # 3. Simulate Ctrl+V
        self._keyboard.press(Key.ctrl_l)
        self._keyboard.press("v")
        self._keyboard.release("v")
        self._keyboard.release(Key.ctrl_l)
        time.sleep(0.1)

        # 4. Restore previous clipboard (deferred — don't race the paste)
        if previous:
            def _restore():
                time.sleep(self._restore_delay_s)
                try:
                    pyperclip.copy(previous)
                except pyperclip.PyperclipException as exc:
                    log_event("warning", "restoring previous clipboard failed",
                              {"error": str(exc)})

            threading.Thread(target=_restore, daemon=True).start()

        return previous if previous else None
