"""Step 2: Build SpeakEasy.exe via PyInstaller, then copy to Desktop.

Builds with whatever interpreter runs this script. Point it at a dedicated
clean venv (.venv-build) so the bundle doesn't drag torch/pandas/tensorflow
from a shared environment:

    .venv-build\\Scripts\\python.exe _build_exe.py
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "SpeakEasy"
# get() with fallback: a bare service/minimal env without USERPROFILE used
# to crash here with KeyError before the build even started (skeptic 2026-09-13).
DESKTOP = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), "Desktop")
ICO = os.path.join(HERE, "icon.ico")
MAIN = os.path.join(HERE, "main.py")

args = [
    sys.executable, "-m", "PyInstaller",
    "--clean", "--noconfirm",
    "--onefile", "--windowed",
    f"--name={APP_NAME}",
    f"--icon={ICO}",
    # --- local modules that are imported lazily (inside functions) ---
    "--hidden-import=settings",
    "--hidden-import=settings_window",
    "--hidden-import=fortnite_guard",
    "--hidden-import=llm_cleanup",
    # --- tray + image ---
    "--collect-submodules=pystray",
    "--hidden-import=pystray._win32",
    "--collect-submodules=PIL",
    # --- input / audio / clipboard ---
    "--hidden-import=pynput",
    "--hidden-import=pyperclip",
    "--hidden-import=sounddevice",
    "--hidden-import=numpy",
    "--hidden-import=tkinter",
    # --- win32: mouse hook (win32gui/process) + autostart shortcut (win32com) ---
    "--hidden-import=win32gui",
    "--hidden-import=win32process",
    "--hidden-import=win32com",
    "--hidden-import=win32com.client",
    "--hidden-import=win32timezone",
    # --- process detection (Fortnite guard) ---
    "--hidden-import=psutil",
    # --- transcription backend: faster-whisper -> ctranslate2 + onnxruntime VAD.
    # These ship native binaries that import-analysis misses; collect explicitly.
    "--collect-data=faster_whisper",
    "--copy-metadata=faster_whisper",
    "--collect-binaries=ctranslate2",
    "--collect-binaries=onnxruntime",
    "--collect-data=onnxruntime",
    "--collect-data=tokenizers",
    MAIN,
]

print("[build] Running PyInstaller (this may take 1-2 minutes)...")
# timeout so a hung PyInstaller fails loudly instead of blocking forever
# (skeptic 2026-09-13); 20 min comfortably covers slow machines.
subprocess.check_call(args, cwd=HERE, timeout=1200)
print("[build] PyInstaller complete.")

# Copy to Desktop (single source of truth for the launchable app).
src = os.path.join(HERE, "dist", f"{APP_NAME}.exe")
os.makedirs(DESKTOP, exist_ok=True)  # skeptic 2026-09-13: missing dir crashed copy2
dst = os.path.join(DESKTOP, f"{APP_NAME}.exe")
shutil.copy2(src, dst)
size_mb = round(os.path.getsize(dst) / (1024 * 1024), 1)
print(f"[build] OK -> {dst}  ({size_mb} MB)")
