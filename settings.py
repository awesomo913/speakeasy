"""SpeakEasy persisted settings + Windows autostart control.

Settings live in %APPDATA%\\SpeakEasy\\settings.json (survives exe rebuilds,
unlike anything next to a one-file exe which unpacks to a temp dir).

Autostart is implemented as a shortcut in the user's Startup folder pointing at
the running executable. Toggling it on creates the shortcut; off removes it.
The shortcut targets whatever is currently running:
  - frozen exe  -> the SpeakEasy.exe itself
  - dev (source) -> pythonw.exe main.py
so a build installed on the user's machine registers the real exe.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from speakeasy_log import log_event

APP_NAME = "SpeakEasy"
DEFAULTS: dict = {
    "autostart": False,
    "dot_x": None,
    "dot_y": None,
    # LLM polish pass: off by default so the app behaves exactly as before
    # until the user opts in + provides a key.
    "llm_cleanup": False,
    "llm_api_key": "",
    "llm_model": "openai/gpt-4o-mini",
    # Status dot visibility: on by default (previous behavior).
    "show_dot": True,
    # Keyboard toggle alongside the mouse side button. Empty string disables it.
    "hotkey": "<ctrl>+<alt>+d",
    # Mouse side-button (XButton1) trigger — on by default (previous behavior).
    "mouse_button": True,
    # Whisper model size. Applies on next launch.
    "model": "small",
    # "auto" lets faster-whisper detect the language; otherwise a 2-letter code.
    "language": "auto",
    # Quit SpeakEasy when a configured game launches (mouse/keyboard hooks can
    # interfere with some anti-cheat or competitive games).
    "game_guard": True,
    "game_processes": ["fortniteclient-win64-shipping.exe", "fortnitelauncher.exe"],
}


# ---------- pure helpers (settings-derived, no I/O — easy to unit test) ----------

def language_to_whisper(language: str) -> str | None:
    """Map the settings "language" value to what faster-whisper expects.

    "auto" (or anything blank) means "let Whisper detect it" -> None.
    Anything else is passed through lower-cased (faster-whisper expects a
    2-letter ISO code such as "en", "es", "fr").
    """
    code = (language or "").strip().lower()
    if not code or code == "auto":
        return None
    return code


def parse_game_processes(raw: str) -> list[str]:
    """Parse a comma-separated process-name string from the settings UI.

    Blank entries are dropped; each name is lower-cased and stripped so it
    matches psutil's process names regardless of how the user typed it.
    """
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


# ---------- settings file ----------

def _settings_dir() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _settings_path() -> Path:
    return _settings_dir() / "settings.json"


def load() -> dict:
    """Return saved settings merged over defaults. Never raises."""
    p = _settings_path()
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**DEFAULTS, **data}
        except (json.JSONDecodeError, OSError) as exc:
            log_event("warning", "settings load failed; using defaults",
                      {"error": str(exc)})
    return dict(DEFAULTS)


def save(data: dict) -> bool:
    """Atomically persist settings. Returns True on success."""
    p = _settings_path()
    tmp = p.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(p)  # atomic on Windows for same-volume replace
        return True
    except OSError as exc:
        log_event("failure", "settings save failed", {"error": str(exc)})
        return False


# ---------- Windows autostart (Startup-folder shortcut) ----------

def _startup_dir() -> Path:
    return (Path(os.environ["APPDATA"])
            / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")


def _shortcut_path() -> Path:
    return _startup_dir() / f"{APP_NAME}.lnk"


def is_autostart_enabled() -> bool:
    """Ground truth = the shortcut actually exists in Startup."""
    try:
        return _shortcut_path().is_file()
    except OSError:
        return False


def _create_shortcut() -> None:
    """Create the Startup shortcut pointing at the current executable.

    Uses WScript.Shell via pywin32 (already a dependency). Raises on failure so
    the caller can surface it — we never want to silently report 'on' when the
    shortcut wasn't actually written.
    """
    import win32com.client  # type: ignore[import-not-found]

    shell = win32com.client.Dispatch("WScript.Shell")
    sc = shell.CreateShortcut(str(_shortcut_path()))
    if getattr(sys, "frozen", False):
        # one-file/one-dir exe: the exe is the launch target.
        sc.TargetPath = sys.executable
        sc.WorkingDirectory = str(Path(sys.executable).parent)
        sc.IconLocation = sys.executable
    else:
        # dev: launch the source with the windowed interpreter.
        pyw = sys.executable
        if pyw.lower().endswith("python.exe"):
            cand = pyw[:-len("python.exe")] + "pythonw.exe"
            if Path(cand).exists():
                pyw = cand
        main_py = Path(__file__).resolve().parent / "main.py"
        sc.TargetPath = pyw
        sc.Arguments = f'"{main_py}"'
        sc.WorkingDirectory = str(main_py.parent)
    sc.Description = "SpeakEasy voice dictation"
    sc.save()


def set_autostart(enabled: bool) -> bool:
    """Enable/disable autostart and persist the choice. Returns True on success.

    The persisted flag is only written to match what we actually achieved on
    disk, so the GUI never shows a state that doesn't reflect reality.
    """
    try:
        if enabled:
            _create_shortcut()
        else:
            sc = _shortcut_path()
            if sc.exists():
                sc.unlink()
    except Exception as exc:  # noqa: BLE001 — report, don't crash the GUI
        log_event("failure", "set_autostart failed",
                  {"enabled": enabled, "error": str(exc)})
        return False

    data = load()
    data["autostart"] = bool(enabled)
    # Propagate the save result: a failed write must NOT report success
    # (skeptic 2026-09-13 — the old `return True` lied to the GUI).
    ok = save(data)
    log_event("decision", "autostart changed", {"enabled": bool(enabled), "ok": ok})
    return ok
