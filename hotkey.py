"""Global keyboard hotkey — an alternative trigger to the mouse side button.

Hotkey strings use pynput's syntax, e.g. "<ctrl>+<alt>+d". An empty string
disables the hotkey.

Why not pynput.keyboard.GlobalHotKeys: on Windows it (a) ignores injected
key events, so AutoHotkey remaps and macro pads can't trigger it, and (b)
misses letter combos, because while Ctrl is held Windows reports a letter as
a bare virtual-key code (or a control character) instead of its character,
which never equals the parsed "d". We run a plain Listener instead and compare
every non-modifier key by virtual-key code on both sides.
"""
from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes

from pynput import keyboard

from speakeasy_log import log_event

DEFAULT_HOTKEY = "<ctrl>+<alt>+d"

def _cursor_position() -> tuple[int, int]:
    """Current mouse position via GetCursorPos, for overlay placement."""
    pt = wintypes.POINT()
    try:
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
    except OSError as exc:
        log_event("warning", "GetCursorPos failed", {"error": str(exc)})
    return 0, 0


# Own prototype: pynput sets argtypes on the shared windll.user32 function object.
_VkKeyScanW = ctypes.WinDLL("user32").VkKeyScanW
_VkKeyScanW.argtypes = [wintypes.WCHAR]
_VkKeyScanW.restype = ctypes.c_short


def _char_to_vk(char: str) -> int | None:
    """Virtual-key code for a printable character on the current layout."""
    try:
        res = _VkKeyScanW(char)
    except (ctypes.ArgumentError, OSError) as exc:
        log_event("warning", "VkKeyScanW failed", {"char": char, "error": str(exc)})
        return None
    if res == -1:
        return None
    return res & 0xFF


def _normalize(key):
    """Reduce any KeyCode to a vk-only KeyCode so press events compare reliably."""
    if isinstance(key, keyboard.KeyCode):
        if key.vk is not None:
            return keyboard.KeyCode.from_vk(key.vk)
        if key.char:
            vk = _char_to_vk(key.char.lower())
            if vk is not None:
                return keyboard.KeyCode.from_vk(vk)
    return key


def parse_hotkey(hotkey: str) -> list | None:
    """Parse a pynput hotkey string into normalized keys, or None if invalid/empty."""
    if not hotkey.strip():
        return None
    try:
        keys = keyboard.HotKey.parse(hotkey)
    except (ValueError, KeyError):
        return None
    normalized = [_normalize(k) for k in keys]
    if any(isinstance(k, keyboard.KeyCode) and k.vk is None for k in normalized):
        return None  # a character we can't map to a key on this layout
    return normalized


def is_valid_hotkey(hotkey: str) -> bool:
    """True if `hotkey` is empty (disabled) or a usable hotkey string."""
    return not hotkey.strip() or parse_hotkey(hotkey) is not None


def format_hotkey(hotkey: str) -> str:
    """Human-readable form: "<ctrl>+<alt>+d" -> "Ctrl + Alt + D"."""
    if not hotkey.strip():
        return "Off"
    parts = []
    for token in hotkey.split("+"):
        name = token.strip().strip("<>")
        if len(name) == 1:
            parts.append(name.upper())
        elif name.isdigit():
            parts.append(f"Key {name}")
        else:
            parts.append({"cmd": "Win", "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift"}
                         .get(name, name.replace("_", " ").title()))
    return " + ".join(parts)


class HotkeyListener:
    """Keyboard listener that fires `on_toggle(x, y)` when the hotkey is pressed.

    `on_toggle` gets the current cursor position, exactly like the mouse hook's
    callback, so main.py doesn't branch on trigger source. Rebind with restart().
    """

    def __init__(self, on_toggle: Callable[[int, int], None]):
        self._on_toggle = on_toggle
        self._listener: keyboard.Listener | None = None
        self._hotkey: keyboard.HotKey | None = None

    def _fire(self) -> None:
        x, y = _cursor_position()
        try:
            self._on_toggle(x, y)
        except Exception as exc:  # noqa: BLE001 — never let a hotkey callback kill the listener
            log_event("failure", "hotkey toggle callback raised", {"error": str(exc)})

    def _key(self, key):
        # KeyCodes: keep the vk (canonical() would drop it for a char event).
        # Keys: canonical() folds ctrl_l/ctrl_r -> ctrl and space -> vk KeyCode,
        # matching what HotKey.parse produced.
        if isinstance(key, keyboard.KeyCode) or self._listener is None:
            return _normalize(key)
        return _normalize(self._listener.canonical(key))

    def _on_press(self, key, _injected=False) -> None:
        if self._hotkey is not None and key is not None:
            self._hotkey.press(self._key(key))

    def _on_release(self, key, _injected=False) -> None:
        if self._hotkey is not None and key is not None:
            self._hotkey.release(self._key(key))

    def start(self, hotkey: str) -> None:
        """Start (or restart) the listener. An empty string leaves the hotkey off."""
        self.stop()
        hotkey = hotkey.strip()
        if not hotkey:
            log_event("state", "hotkey disabled", {})
            return
        keys = parse_hotkey(hotkey)
        if keys is None:
            log_event("warning", "invalid hotkey string; hotkey disabled", {"hotkey": hotkey})
            return
        try:
            self._hotkey = keyboard.HotKey(keys, self._fire)
            self._listener = keyboard.Listener(on_press=self._on_press,
                                               on_release=self._on_release)
            self._listener.daemon = True
            self._listener.start()
            log_event("state", "hotkey listener started", {"hotkey": hotkey})
        except Exception as exc:  # noqa: BLE001 — a bad binding must not crash startup
            log_event("failure", "hotkey listener failed to start",
                      {"hotkey": hotkey, "error": str(exc)})
            self._listener = None
            self._hotkey = None

    def restart(self, hotkey: str) -> None:
        """Rebind live — settings changed the hotkey string."""
        self.start(hotkey)

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception as exc:  # noqa: BLE001 — stop must never raise into shutdown
                log_event("warning", "hotkey listener stop raised", {"error": str(exc)})
        self._listener = None
        self._hotkey = None
