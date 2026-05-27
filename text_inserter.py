"""Clipboard-based text insertion — saves old clipboard, copies new text, simulates Ctrl+V."""
import time

import pyperclip
from pynput.keyboard import Controller, Key


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
        except Exception:
            previous = ""

        # 2. Copy our text to clipboard
        pyperclip.copy(text)
        time.sleep(0.05)

        # 3. Simulate Ctrl+V
        self._keyboard.press(Key.ctrl_l)
        self._keyboard.press("v")
        self._keyboard.release("v")
        self._keyboard.release(Key.ctrl_l)
        time.sleep(0.1)

        # 4. Restore previous clipboard (deferred)
        if previous is not None:
            # schedule restore — we don't want to race the paste
            def _restore():
                time.sleep(self._restore_delay_s)
                try:
                    pyperclip.copy(previous)
                except Exception:
                    pass

            import threading
            t = threading.Thread(target=_restore, daemon=True)
            t.start()

        return previous if previous else None
