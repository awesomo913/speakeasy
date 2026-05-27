"""Install dependencies for AutoMic."""
import subprocess
import sys

deps = [
    "numpy",
    "pynput",
    "sounddevice",
    "webrtcvad",
    "faster-whisper",
    "pyperclip",
]

for dep in deps:
    print(f"Installing {dep}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", dep])

print("All dependencies installed.")
