import subprocess, sys

deps = ["numpy", "pynput", "sounddevice", "pyperclip", "vosk", "pyinstaller", "Pillow"]

for d in deps:
    print(f"[INSTALLING] {d}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", d])

print("\n✅ All ready.")
