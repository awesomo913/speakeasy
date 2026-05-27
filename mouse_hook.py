"""Global mouse listener — the BOTTOM side button (XButton1) toggles dictation.

The bottom side button is swallowed system-wide so it never triggers its default
Back action in any app, EXCEPT when Fortnite is the foreground window. In Fortnite
the button passes through untouched (and does NOT toggle dictation), so in-game
rebinds keep working. (The TOP side button, XButton2, is left entirely alone so
it stays free for Fortnite.)

Windows side-button mapping:
    XButton1 (=1) → front/bottom button, default "Back"     (our trigger)
    XButton2 (=2) → rear/top button,    default "Forward"   (left alone here)
"""
import ctypes
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

from pynput import mouse

try:
    # main.py installs the logger and adds ~/.claude/scripts to sys.path before
    # importing this module. No-op fallback if imported standalone in dev.
    from crash_logger import log_event
except Exception:  # pragma: no cover
    def log_event(*_args, **_kwargs):
        pass


_WM_XBUTTONDOWN = 0x020B
_WM_XBUTTONUP = 0x020C
_XBUTTON1 = 1  # bottom side button ("back") — our trigger

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _foreground_exe() -> str:
    """Full path of the exe owning the foreground window ('' if it can't be read)."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = _kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
    )
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(len(buf))
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        _kernel32.CloseHandle(handle)


def _is_fortnite_foreground() -> bool:
    """True when the active window belongs to the Fortnite client."""
    return "fortnite" in _foreground_exe().lower()


class MouseHook:
    """Top side button → dictation toggle, suppressed everywhere except Fortnite."""

    def __init__(self, on_toggle: Callable[[int, int], None], debounce_s: float = 0.35):
        self._on_toggle = on_toggle
        self._debounce_s = debounce_s
        self._last_press = 0.0
        self._listener: mouse.Listener | None = None
        self._thread: threading.Thread | None = None

    def _event_filter(self, msg: int, data) -> bool:
        """Low-level hook filter. Runs for EVERY mouse event — keep it cheap."""
        # Fast path: anything that isn't a side-button message passes straight through.
        if msg not in (_WM_XBUTTONDOWN, _WM_XBUTTONUP):
            return True
        if (data.mouseData >> 16) != _XBUTTON1:
            return True  # top side button (x2) and others: leave untouched

        # Bottom side button. In Fortnite, let the game have it (no dictation toggle).
        if _is_fortnite_foreground():
            return True

        # Everywhere else: toggle on press-down, then swallow the event so no app
        # sees a Forward/Back. Fire the toggle BEFORE suppress_event(), which raises
        # to stop the event propagating system-wide (covers both down and up).
        if msg == _WM_XBUTTONDOWN:
            now = time.monotonic()
            if now - self._last_press >= self._debounce_s:
                self._last_press = now
                try:
                    self._on_toggle(int(data.pt.x), int(data.pt.y))
                except Exception as exc:
                    log_event("failure", "toggle callback raised", {"error": str(exc)})
        self._listener.suppress_event()
        return True  # unreachable: suppress_event() raised

    def start(self) -> None:
        """Launch the global listener on a daemon thread."""
        self._listener = mouse.Listener(
            on_click=lambda *args: None,  # toggling is handled in the filter
            win32_event_filter=self._event_filter,
        )
        self._thread = threading.Thread(target=self._listener.start, daemon=True)
        self._thread.start()
        log_event("state", "mouse hook started",
                  {"trigger": "XButton1", "suppress_default": True})

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
