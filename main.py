"""SpeakEasy — mouse/hotkey-triggered voice dictation.

The mouse "Back" side button (XButton1), and/or a configurable keyboard
hotkey, toggle the microphone. Records until triggered again OR 10 seconds
of silence. Transcribes locally via faster-whisper, then pastes at cursor.

Usage:  python main.py
"""

import ctypes
import queue
import signal
import sys
import time
from enum import Enum, auto

from speakeasy_log import get_recent_crashes, install, log_event

install(session_name=f"exe_SpeakEasy_{time.strftime('%Y%m%d_%H%M%S')}")

from audio_capture import AudioCapture  # noqa: E402 — logger must install first
from game_guard import GameGuard  # noqa: E402
from hotkey import HotkeyListener  # noqa: E402
from mouse_hook import MouseHook  # noqa: E402
from overlay import Overlay  # noqa: E402
from status_dot import StatusDot  # noqa: E402
from text_inserter import TextInserter  # noqa: E402
from transcription import Transcriber  # noqa: E402
from tray import Tray  # noqa: E402
from version import __version__  # noqa: E402

try:
    import settings as _settings
except Exception:  # pragma: no cover — dev-standalone fallback
    _settings = None

try:
    import llm_cleanup as _llm
except Exception:  # pragma: no cover
    _llm = None


# Max length of a single recording before it auto-stops (safety cap for long
# dictation — was 60s, which cut people off mid-sentence).
MAX_RECORDING_S = 600.0

# Holds the single-instance mutex handle for the life of the process.
_SINGLE_INSTANCE_MUTEX = None


def _acquire_single_instance(name: str = "SpeakEasy_singleton_mutex") -> bool:
    """Return True if we are the only instance; False if one is already running."""
    global _SINGLE_INSTANCE_MUTEX
    kernel32 = ctypes.windll.kernel32
    _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, name)
    if not _SINGLE_INSTANCE_MUTEX:
        # Couldn't create the lock at all — don't pretend it's free (which would
        # let unlimited copies start). Fail open (allow this one) but record it.
        log_event("warning", "CreateMutexW failed", {"error": kernel32.GetLastError()})
        return True
    ERROR_ALREADY_EXISTS = 183
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


# ═══════════════════════════════════════════════════════════════════
# State Machine
# ═══════════════════════════════════════════════════════════════════

class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    PASTING = auto()


class SpeakEasyApp:
    """Top-level orchestrator."""

    def __init__(self):
        self.state = State.IDLE
        self._cmd_queue: queue.Queue = queue.Queue()

        # subsystems
        self.overlay = Overlay()
        self.transcriber = Transcriber()
        self.inserter = TextInserter()

        # audio capture — created on demand
        self._audio: AudioCapture | None = None
        self._wav_data: bytes = b""
        # last raw transcript, kept so a failed LLM polish can fall back
        # to pasting the unpolished text instead of losing the dictation
        self._raw_text: str = ""

        settings_now = _settings.load() if _settings else {}

        # mouse hook + keyboard hotkey — both feed the same toggle
        self._hook = MouseHook(
            on_toggle=self._on_toggle,
            enabled=bool(settings_now.get("mouse_button", True)),
        )
        self._hotkey = HotkeyListener(on_toggle=self._on_toggle)

        # Game guard: a global mouse/keyboard hook can glitch input in some
        # games, so we quit the whole app when a configured process launches.
        # The user relaunches afterward.
        self._guard = GameGuard(
            on_detected=lambda: self._cmd_queue.put("shutdown"),
            processes=settings_now.get("game_processes", []),
        )
        self._game_guard_enabled = bool(settings_now.get("game_guard", True))

        # system-tray control (pause/resume + quit)
        self._paused = False
        self._tray = Tray(
            on_toggle_pause=lambda: self._cmd_queue.put("toggle_pause"),
            on_quit=lambda: self._cmd_queue.put("shutdown"),
            is_paused=lambda: self._paused,
            on_settings=lambda: self._cmd_queue.put("open_settings"),
        )

        # persistent taskbar-corner status dot — always visible, unlike the
        # cursor-following overlay which only shows during an action
        self.status_dot = StatusDot(
            self.overlay.get_root(),
            on_toggle_pause=lambda: self._cmd_queue.put("toggle_pause"),
            on_settings=lambda: self._cmd_queue.put("open_settings"),
            on_quit=lambda: self._cmd_queue.put("shutdown"),
        )

        # last cursor position for overlay placement
        self._cursor_x: int = 0
        self._cursor_y: int = 0

        # shutdown flag
        self._shutdown = False

    # ------------------------------------------------------------------
    def _set_state(self, new: "State") -> None:
        """Single choke point for state changes so every transition is logged."""
        old = self.state
        if old is new:
            return
        self.state = new
        log_event("state", f"{old.name} -> {new.name}",
                  {"from": old.name, "to": new.name})
        self.status_dot.set_state(new, self._paused)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        print(f"[SpeakEasy] v{__version__} starting... "
              "(press the mouse side-button or hotkey to toggle mic)")
        print("[SpeakEasy] First run downloads the Whisper model (one time)")

        # Self-diagnosis: note if a recent run crashed (no console in the exe,
        # so this goes to the log rather than the screen).
        recent = get_recent_crashes()
        if recent:
            log_event("warning", "previous run(s) crashed", {"count": len(recent)})
        log_event("state", "app starting",
                  {"frozen": getattr(sys, "frozen", False), "version": __version__})

        # Pre-load model so first transcription isn't slow
        print("[SpeakEasy] Pre-loading transcription model...")
        self.transcriber.ensure_loaded()
        print("[SpeakEasy] Model ready.")

        # start tray icon (pause/resume + quit), status dot, and input triggers
        self._tray.start()
        self._refresh_dot()
        self._hook.start()
        self._hotkey.start(_settings.load().get("hotkey", "") if _settings else "")
        if self._game_guard_enabled:
            self._guard.start()

        # signal handlers for clean exit
        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

        # main event loop
        self._run_loop()

    def shutdown(self):
        self._shutdown = True
        if self._audio and self._audio.is_recording():
            self._audio.stop()
        self._hook.stop()
        self._hotkey.stop()
        self._guard.stop()
        self._tray.stop()
        self.status_dot.destroy()
        self.overlay.destroy()

    # ------------------------------------------------------------------
    # Callbacks (from non-main threads → enqueue)
    # ------------------------------------------------------------------
    def _on_toggle(self, x: int = 0, y: int = 0):
        """Called by the mouse hook or hotkey listener thread."""
        self._cursor_x, self._cursor_y = x, y
        self._cmd_queue.put("toggle")

    def _on_signal(self, signum, frame):
        self._cmd_queue.put("shutdown")

    def _on_silence_detected(self):
        """Called from audio thread when silence timeout reached."""
        self._cmd_queue.put("toggle")

    # ------------------------------------------------------------------
    # Main event loop (main thread, tkinter-compatible)
    # ------------------------------------------------------------------
    def _run_loop(self):
        while not self._shutdown:
            # drain command queue
            try:
                while True:
                    cmd = self._cmd_queue.get_nowait()
                    should_exit = self._process_cmd(cmd)
                    if should_exit:
                        return
            except queue.Empty:
                pass

            # process tk events so overlay renders
            self.overlay.run_one_tick()
            time.sleep(0.02)

    def _process_cmd(self, cmd) -> bool:
        """Process a single command. Returns True if app should exit."""
        if cmd == "toggle":
            self._handle_toggle()
        elif cmd == "toggle_pause":
            self._handle_pause()
        elif cmd == "open_settings":
            self._open_settings()
        elif cmd == "refresh_dot":
            self._refresh_dot()
        elif cmd == "settings_changed":
            self._apply_live_settings()
        elif cmd == "shutdown":
            self.shutdown()
            return True
        elif isinstance(cmd, tuple):
            kind = cmd[0]
            if kind == "transcribe_result":
                self._on_transcription_result(cmd[1])
            elif kind == "transcribe_error":
                self._on_transcription_error(cmd[1])
            elif kind == "polish_result":
                self._on_polish_result(cmd[1])
            elif kind == "polish_error":
                self._on_polish_error(cmd[1])
        return False

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------
    def _handle_toggle(self):
        if self._paused:
            return  # listening is paused from the tray — ignore the trigger
        if self.state == State.IDLE:
            self._start_recording()
        elif self.state == State.RECORDING:
            self._stop_and_transcribe()
        # TRANSCRIBING and PASTING — ignore toggles

    def _handle_pause(self):
        """Toggle paused state (from tray). Pausing also stops any live recording."""
        self._paused = not self._paused
        log_event("state", "pause toggled", {"paused": self._paused})
        if self._paused and self.state == State.RECORDING and self._audio:
            self._audio.stop()
            self._audio = None
            self._set_state(State.IDLE)
            self.overlay.hide()
        self._tray.refresh()
        self.status_dot.set_state(self.state, self._paused)

    def _open_settings(self):
        """Open the settings window on the main thread (tkinter-safe)."""
        try:
            from settings_window import open_settings_window
            open_settings_window(
                self.overlay.get_root(),
                on_dot_toggle=lambda: self._cmd_queue.put("refresh_dot"),
                on_settings_saved=lambda: self._cmd_queue.put("settings_changed"),
            )
        except Exception as exc:  # noqa: BLE001 — never crash the loop on UI error
            log_event("failure", "open settings failed", {"error": str(exc)})

    def _refresh_dot(self) -> None:
        """Apply the show_dot preference live (called at startup + on GUI toggle)."""
        try:
            show = bool(_settings.load().get("show_dot", True)) if _settings else True
        except Exception as exc:  # noqa: BLE001 — a bad settings file must not hide the dot
            log_event("warning", "reading show_dot setting failed; defaulting to visible",
                      {"error": str(exc)})
            show = True
        self.status_dot.set_visible(show)
        if show:
            self.status_dot.set_state(self.state, self._paused)
        log_event("state", "status dot visibility applied", {"visible": show})

    def _apply_live_settings(self) -> None:
        """Re-apply settings that can change without a restart (hotkey, triggers, guard)."""
        if _settings is None:
            return
        try:
            data = _settings.load()
        except Exception as exc:  # noqa: BLE001
            log_event("warning", "live settings reload failed", {"error": str(exc)})
            return
        self._hook.set_enabled(bool(data.get("mouse_button", True)))
        self._hotkey.restart(data.get("hotkey", ""))
        # Always rebuild the guard so an edited process list takes effect live.
        want_guard = bool(data.get("game_guard", True))
        if self._game_guard_enabled:
            self._guard.stop()
        self._guard = GameGuard(
            on_detected=lambda: self._cmd_queue.put("shutdown"),
            processes=data.get("game_processes", []),
        )
        if want_guard:
            self._guard.start()
        self._game_guard_enabled = want_guard
        log_event("state", "live settings applied", {})

    def _llm_cleanup_enabled(self) -> bool:
        """True only when the user opted in AND provided a key (else raw paste)."""
        if _llm is None or _settings is None:
            return False
        try:
            data = _settings.load()
        except Exception as exc:  # noqa: BLE001 — a bad settings file must not crash a paste
            log_event("warning", "reading llm settings failed; skipping polish",
                      {"error": str(exc)})
            return False
        return bool(data.get("llm_cleanup")) and bool(data.get("llm_api_key", "").strip())

    def _start_recording(self):
        print("[SpeakEasy] Recording started...")
        self._set_state(State.RECORDING)
        self.overlay.state_recording(self._cursor_x, self._cursor_y)

        self._audio = AudioCapture(
            silence_timeout_s=10.0,
            max_duration_s=MAX_RECORDING_S,
            on_silence=self._on_silence_detected,
        )
        self._audio.start()

    def _stop_and_transcribe(self):
        if not self._audio:
            return

        print("[SpeakEasy] Stopping recording...")
        self._wav_data = self._audio.stop()
        self._audio = None

        if len(self._wav_data) < 1024:  # too short / empty
            print("[SpeakEasy] No speech detected.")
            self.overlay.state_error(
                "No speech detected — try again", self._cursor_x, self._cursor_y,
            )
            self._set_state(State.IDLE)
            self.status_dot.flash_error(self.state, self._paused)
            return

        print(f"[SpeakEasy] Transcribing {len(self._wav_data)} bytes...")
        self._set_state(State.TRANSCRIBING)
        self.overlay.state_transcribing(self._cursor_x, self._cursor_y)

        # async transcription
        self.transcriber.transcribe_async(
            self._wav_data,
            on_done=lambda text: self._cmd_queue.put(("transcribe_result", text)),
            on_error=lambda exc: self._cmd_queue.put(("transcribe_error", exc)),
        )

    def _on_transcription_result(self, text: str):
        print(f"[SpeakEasy] Transcribed: '{text}'")
        if not text.strip():
            self.overlay.state_error("Transcription was empty", self._cursor_x, self._cursor_y)
            self._set_state(State.IDLE)
            self.status_dot.flash_error(self.state, self._paused)
            return

        self._raw_text = text  # keep for fallback if the polish pass fails

        if self._llm_cleanup_enabled():
            print("[SpeakEasy] Polishing with LLM...")
            self._set_state(State.TRANSCRIBING)
            self.overlay.state_transcribing(self._cursor_x, self._cursor_y)
            data = _settings.load()
            _llm.clean_async(
                text,
                api_key=data.get("llm_api_key", ""),
                model=data.get("llm_model", "openai/gpt-4o-mini"),
                on_done=lambda polished: self._cmd_queue.put(("polish_result", polished)),
                on_error=lambda exc: self._cmd_queue.put(("polish_error", exc)),
            )
            return

        self._paste_text(text)

    def _paste_text(self, text: str) -> None:
        """Single choke point for all pasting (raw or polished)."""
        self._set_state(State.PASTING)
        self.overlay.state_pasting(preview=text, x=self._cursor_x, y=self._cursor_y)
        try:
            self.inserter.paste(text)
        except Exception as exc:  # noqa: BLE001 — a clipboard failure must not crash the loop
            log_event("failure", "pasting transcript failed", {"error": str(exc)})
            self.overlay.state_error(
                "Couldn't paste — clipboard access failed", self._cursor_x, self._cursor_y,
            )
            self.status_dot.flash_error(State.IDLE, self._paused)
        self._set_state(State.IDLE)

    def _on_polish_result(self, text: str):
        polished = (text or "").strip()
        if not polished:
            # Empty polish = fall back to raw, never paste nothing.
            log_event("warning", "llm polish empty; using raw transcript")
            polished = self._raw_text
        print(f"[SpeakEasy] Polished: '{polished}'")
        self._paste_text(polished)

    def _on_polish_error(self, exc: Exception):
        print(f"[SpeakEasy] Polish failed, pasting raw: {exc}")
        log_event("warning", "llm polish failed; using raw transcript",
                  {"error": str(exc)})
        self._paste_text(self._raw_text)

    def _on_transcription_error(self, exc: Exception):
        print(f"[SpeakEasy] Transcription error: {exc}")
        log_event("failure", "transcription failed", {"error": str(exc)})
        self.overlay.state_error(f"Transcription failed: {exc}", self._cursor_x, self._cursor_y)
        self._set_state(State.IDLE)
        self.status_dot.flash_error(self.state, self._paused)


# ═══════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════

def main():
    # Only allow one copy at a time — double-clicking the exe again is a no-op
    # instead of spawning a second listener that fights over the microphone.
    if not _acquire_single_instance():
        log_event("state", "second instance blocked")
        print("[SpeakEasy] SpeakEasy is already running (tray icon).")
        return

    app = SpeakEasyApp()
    try:
        app.start()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()
        print("[SpeakEasy] Goodbye.")


if __name__ == "__main__":
    main()
