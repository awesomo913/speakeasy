"""Quit SpeakEasy automatically when a configured game launches.

SpeakEasy uses a global low-level mouse hook (mouse_hook) to catch the side
button, and optionally a global keyboard hook (hotkey) for the keyboard
toggle. A low-level hook sits in the input-delivery path of *every* click or
keypress, and in a competitive/twitch game that can look like input glitches
to anti-cheat or just cause dropped clicks. Rather than weaken the hooks, we
shut the whole app down when a configured game process appears — no hook
running means no possible interference. The user relaunches SpeakEasy when
they're done playing.

Detection is by process name (polled), not foreground window, so we quit as
soon as the game starts loading rather than waiting for it to grab focus.

The process list is user-configurable via settings ("game_processes"); the
default covers Fortnite as a well-known example.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

from speakeasy_log import log_event

_DEFAULT_POLL_S = 3.0  # not latency-sensitive; cheap process scan


def _normalize(procs: Iterable[str]) -> frozenset[str]:
    """Lower-case + strip every entry so settings-file typos still match."""
    return frozenset(p.strip().lower() for p in procs if p and p.strip())


def _matching_process(procs: frozenset[str]) -> str | None:
    """Return the name of a running process from `procs`, or None.

    Uses psutil (already bundled with the app). On any failure we return None
    — a detection miss just means SpeakEasy keeps running, which is the safe,
    non-destructive default (we never want a false positive to kill the app
    mid-dictation).
    """
    try:
        import psutil
    except ImportError as exc:
        log_event("warning", "game guard: psutil unavailable", {"error": str(exc)})
        return None
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in procs:
                return name
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception as exc:  # noqa: BLE001 — one bad proc must not abort the scan
            log_event("warning", "game guard: process scan entry failed", {"error": str(exc)})
            continue
    return None


class GameGuard:
    """Background poller that fires ``on_detected`` once a configured game appears."""

    def __init__(
        self,
        on_detected: Callable[[], None],
        processes: Iterable[str],
        poll_interval_s: float = _DEFAULT_POLL_S,
    ):
        self._on_detected = on_detected
        self._processes = _normalize(processes)
        self._interval = poll_interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _fire(self, matched: str) -> None:
        log_event("decision", "guarded game detected -> quitting SpeakEasy",
                  {"process": matched, "reason": "avoid input-hook interference"})
        try:
            self._on_detected()
        except Exception as exc:  # noqa: BLE001 — never let the callback crash the poller
            log_event("failure", "game guard on_detected raised", {"error": str(exc)})

    def _loop(self) -> None:
        if not self._processes:
            return
        # Immediate check on startup: if the user launched SpeakEasy while the
        # game was already running, quit right away instead of waiting a full
        # interval.
        matched = _matching_process(self._processes)
        if matched:
            self._fire(matched)
            return
        while not self._stop.wait(self._interval):
            try:
                matched = _matching_process(self._processes)
                if matched:
                    self._fire(matched)
                    return  # one-shot — we're shutting the app down
            except Exception as exc:  # noqa: BLE001
                log_event("failure", "game guard poll raised", {"error": str(exc)})

    def start(self) -> None:
        if not self._processes:
            log_event("state", "game guard skipped", {"reason": "no processes configured"})
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="GameGuard")
        self._thread.start()
        log_event("state", "game guard started",
                  {"interval_s": self._interval, "procs": sorted(self._processes)})

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=1.0)
