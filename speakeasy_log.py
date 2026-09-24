"""speakeasy_log.py — self-contained crash/event logger for SpeakEasy.

Standalone module (no dependency on any developer machine's personal tooling)
so the app behaves the same for every user who clones the repo.

Usage (at the top of main.py):

    from speakeasy_log import install, log_event, get_recent_crashes

    install()

    # ...app runs...

    log_event("warning", "settings load failed", {"error": str(exc)})

On any uncaught exception, a full traceback + env snapshot is written to the
log directory as newline-delimited JSON.

Log directory resolution (both dev and frozen-exe runs):
    1. %LOCALAPPDATA%\\SpeakEasy\\logs   (normal Windows install)
    2. ~/.speakeasy/logs                 (fallback if LOCALAPPDATA is unset)

Log categories (written as ``{"level": "<category>", ...}``):
    crash      — uncaught exception, program state lost
    failure    — handled error, recovered but feature broken
    glitch     — visual/state anomaly, didn't crash
    warning    — potentially problematic, watch this
    state      — normal state transition
    decision   — a branching choice the program made
    perf       — a timed operation
    boundary   — crossing in/out of process (HTTP, subprocess, file I/O)
    learning   — a fact worth remembering
"""
from __future__ import annotations

import atexit
import datetime as _dt
import json
import os
import platform
import sys
import traceback
from pathlib import Path
from typing import Any

_log_dir: Path | None = None
_session_file: Path | None = None
_original_excepthook = sys.excepthook


def _timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def default_log_dir() -> Path:
    """Where SpeakEasy logs live: %LOCALAPPDATA%\\SpeakEasy\\logs, else ~/.speakeasy/logs."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "SpeakEasy" / "logs"
    return Path.home() / ".speakeasy" / "logs"


def _write(record: dict[str, Any]) -> None:
    if _session_file is None:
        return
    try:
        _session_file.parent.mkdir(parents=True, exist_ok=True)
        with _session_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass  # never let the logger itself raise


def install(log_dir: Path | None = None, session_name: str | None = None) -> Path:
    """Install the global exception handler + session log file.

    Returns the path to the session log so callers can reference it.
    """
    global _log_dir, _session_file

    _log_dir = Path(log_dir) if log_dir is not None else default_log_dir()
    _log_dir.mkdir(parents=True, exist_ok=True)

    ts = _timestamp()
    fname = f"session_{session_name or ts}.log"
    _session_file = _log_dir / fname

    _write({
        "level": "session_start",
        "timestamp": _dt.datetime.now().isoformat(),
        "log_dir": str(_log_dir),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pid": os.getpid(),
    })

    sys.excepthook = _excepthook

    # threading.excepthook — uncaught exceptions in worker threads.
    try:
        import threading

        def _thread_hook(args):
            _write({
                "level": "crash",
                "timestamp": _dt.datetime.now().isoformat(),
                "exc_type": args.exc_type.__name__ if args.exc_type else "Unknown",
                "exc_value": str(args.exc_value),
                "thread": getattr(args.thread, "name", "?"),
                "traceback": "".join(traceback.format_exception(
                    args.exc_type, args.exc_value, args.exc_traceback)),
            })
            threading.__excepthook__(args)

        threading.excepthook = _thread_hook
    except Exception as exc:  # noqa: BLE001 — logger install must never crash the app
        _write({"level": "warning", "timestamp": _dt.datetime.now().isoformat(),
                "message": "threading.excepthook install failed", "error": str(exc)})

    # tkinter callback exceptions — go to Tk.report_callback_exception, not
    # sys.excepthook. Without this, a crash inside a button/after() handler
    # only prints to stderr (invisible in a windowed exe with no console).
    try:
        import tkinter as _tk

        def _tk_callback_exc(_self, exc_type, exc_value, exc_tb):
            _write({
                "level": "crash",
                "timestamp": _dt.datetime.now().isoformat(),
                "exc_type": exc_type.__name__ if exc_type else "Unknown",
                "exc_value": str(exc_value),
                "source": "tkinter callback",
                "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
            })
            traceback.print_exception(exc_type, exc_value, exc_tb)

        _tk.Tk.report_callback_exception = _tk_callback_exc
    except Exception as exc:  # noqa: BLE001
        _write({"level": "warning", "timestamp": _dt.datetime.now().isoformat(),
                "message": "tkinter callback hook install failed", "error": str(exc)})

    atexit.register(_on_exit)
    return _session_file


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    """Capture uncaught exceptions, write a crash log, then delegate."""
    try:
        _write({
            "level": "crash",
            "timestamp": _dt.datetime.now().isoformat(),
            "exc_type": exc_type.__name__ if exc_type else "Unknown",
            "exc_value": str(exc_value),
            "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        })
    finally:
        _original_excepthook(exc_type, exc_value, exc_tb)


def _on_exit() -> None:
    _write({"level": "session_end", "timestamp": _dt.datetime.now().isoformat()})


def log_event(level: str, message: str, context: dict[str, Any] | None = None) -> None:
    """Log a non-fatal event: failure | glitch | warning | state | decision | perf | boundary."""
    _write({
        "level": level,
        "timestamp": _dt.datetime.now().isoformat(),
        "message": message,
        "context": context or {},
    })


def get_recent_crashes(log_dir: Path | None = None, n: int = 5) -> list[dict]:
    """Return the N most recent crash/failure records across all session logs.

    The app calls this at startup to self-diagnose ("last run crashed at X").
    """
    root = Path(log_dir) if log_dir is not None else default_log_dir()
    if not root.is_dir():
        return []
    records: list[dict] = []
    for log_file in sorted(root.glob("session_*.log"), reverse=True):
        try:
            with log_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("level") in ("crash", "failure"):
                        rec["_source"] = log_file.name
                        records.append(rec)
                        if len(records) >= n:
                            return records
        except OSError:
            continue
    return records
