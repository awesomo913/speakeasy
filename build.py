"""Build SpeakEasy.exe — a standalone Windows executable.

Builds with whatever interpreter runs this script. Point it at a dedicated
clean venv (.venv-build) so the bundle doesn't drag unrelated packages from a
shared environment:

    .venv-build\\Scripts\\python.exe build.py

Output: dist\\SpeakEasy.exe only (no copies elsewhere — CI picks it up from
dist\\ for releases; a local install is the user's own choice).
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "SpeakEasy"
ICO = os.path.join(HERE, "icon.ico")
MAIN = os.path.join(HERE, "main.py")

# Hidden imports that PyInstaller's static import-analysis misses because
# these modules are imported lazily (inside functions) or ship native binaries.
_HIDDEN_IMPORTS = [
    # --- local modules imported lazily (inside functions) ---
    "settings",
    "settings_window",
    "game_guard",
    "hotkey",
    "llm_cleanup",
    "theme",
    "version",
    "speakeasy_log",
    # --- tray + image ---
    "pystray._win32",
    # --- input / audio / clipboard ---
    "pynput",
    "pyperclip",
    "sounddevice",
    "numpy",
    "tkinter",
    # --- win32: mouse/keyboard hooks + autostart shortcut (win32com) ---
    "win32gui",
    "win32process",
    "win32com",
    "win32com.client",
    "win32timezone",
    # --- process detection (game guard) ---
    "psutil",
]

_COLLECT_SUBMODULES = ["pystray", "PIL"]


def _ensure_icon() -> None:
    """Regenerate the icon if it's missing (fresh clone before first build)."""
    if os.path.isfile(ICO):
        return
    print("[build] icon.ico missing — generating it first...")
    subprocess.check_call(
        [sys.executable, os.path.join(HERE, "scripts", "make_icon.py")], cwd=HERE,
    )


def build_exe() -> None:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--clean", "--noconfirm",
        "--onefile", "--windowed",
        f"--name={APP_NAME}",
        f"--icon={ICO}",
    ]
    for mod in _HIDDEN_IMPORTS:
        args.append(f"--hidden-import={mod}")
    for pkg in _COLLECT_SUBMODULES:
        args.append(f"--collect-submodules={pkg}")

    # Transcription backend: faster-whisper -> ctranslate2 + onnxruntime VAD.
    # These ship native binaries that import-analysis misses; collect explicitly.
    args += [
        "--collect-data=faster_whisper",
        "--copy-metadata=faster_whisper",
        "--collect-binaries=ctranslate2",
        "--collect-binaries=onnxruntime",
        "--collect-data=onnxruntime",
        "--collect-data=tokenizers",
        MAIN,
    ]

    print("[build] Running PyInstaller (this may take 1-2 minutes)...")
    # Timeout so a hung PyInstaller fails loudly instead of blocking forever;
    # 20 minutes comfortably covers slow machines / cold caches.
    subprocess.check_call(args, cwd=HERE, timeout=1200)
    print("[build] PyInstaller complete.")


def main() -> None:
    _ensure_icon()
    build_exe()

    exe_path = os.path.join(HERE, "dist", f"{APP_NAME}.exe")
    if not os.path.isfile(exe_path):
        raise SystemExit(f"[build] FAILED: expected {exe_path} but it doesn't exist")
    size_mb = round(os.path.getsize(exe_path) / (1024 * 1024), 1)
    print(f"[build] OK -> {exe_path}  ({size_mb} MB)")


if __name__ == "__main__":
    main()
