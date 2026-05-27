"""Quit SpeakEasy automatically when Fortnite launches.

SpeakEasy uses a global low-level mouse hook (mouse_hook) to catch the side
button. A low-level hook sits in the input-delivery path of *every* click, and
in a twitch shooter that can show up as left-click glitches. Rather than weaken
the hook, we simply shut the whole app down when the Fortnite client appears —
no hook running means no possible interference. The user relaunches SpeakEasy
from the control GUI after they're done playing.

Detection is by process name (polled), not foreground window, so we quit as
soon as the game starts loading rather than waiting for it to grab focus.
"""
import threading
import time
from collections.abc import Callable

try:
    # main.py installs the logger and adds ~/.claude/scripts to sys.path before
    # importing this module. No-op fallback if imported standalone in dev.
    from crash_logger import log_event
except Exception:  # pragma: no cover
    def log_event(*_args, **_kwargs):
        pass


# Lower-cased process names that mean "Fortnite is up". The shipping client is
# the process that actually captures raw game input; the launcher is included
# so we bail out during the load screen, before the match starts.
_FORTNITE_PROCS = frozenset({
    "fortniteclient-win64-shipping.exe",
    "fortnitelauncher.exe",
})

_DEFAULT_POLL_S = 3.0  # not latency-sensitive; cheap process scan


def _fortnite_running() -> bool:
    """True if any Fortnite process is currently running.

    Uses psutil (already bundled with the app). On any failure we return False
    — a detection miss just means SpeakEasy keeps running, which is the safe,
    non-destructive default (we never want a false positive to kill the app
    while the user is mid-dictation).
    """
    try:
        import psutil
    except ImportError:
        return False
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in _FORTNITE_PROCS:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:  # noqa: BLE001 — never let one bad proc abort the scan
            continue
    return False


class FortniteGuard:
    """Background poller that fires ``on_detected`` once when Fortnite appears."""

    def __init__(
        self,
        on_detected: Callable[[], None],
        poll_interval_s: float = _DEFAULT_POLL_S,
    ):
        self._on_detected = on_detected
        self._interval = poll_interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _fire(self) -> None:
        log_event("decision", "fortnite detected -> quitting SpeakEasy",
                  {"reason": "avoid mouse-hook glitch in game"})
        try:
            self._on_detected()
        except Exception as exc:  # never let the callback crash the poller
            log_event("failure", "fortnite on_detected raised", {"error": str(exc)})

    def _loop(self) -> None:
        # Immediate check on startup: if the user launched SpeakEasy while
        # Fortnite was already running, quit right away instead of waiting a
        # full interval.
        if _fortnite_running():
            self._fire()
            return
        while not self._stop.wait(self._interval):
            try:
                if _fortnite_running():
                    self._fire()
                    return  # one-shot — we're shutting the app down
            except Exception as exc:  # noqa: BLE001
                log_event("failure", "fortnite guard poll raised", {"error": str(exc)})

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="FortniteGuard"
        )
        self._thread.start()
        log_event("state", "fortnite guard started",
                  {"interval_s": self._interval, "procs": sorted(_FORTNITE_PROCS)})

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=1.0)
