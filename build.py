"""Build SpeakEasy.exe — standalone Windows executable with custom icon.

Run:  python build.py
Output: SpeakEasy.exe on the desktop + in voice_input/dist/
"""
import os
import shutil
import subprocess
import sys
import tempfile

APP_NAME = "SpeakEasy"
DESKTOP = os.path.join(os.environ["USERPROFILE"], "Desktop")
HERE = os.path.dirname(os.path.abspath(__file__))

# ── Step 1: Generate icon ──────────────────────────────────────────
def create_icon():
    """Generate a fun mic icon as .ico using Pillow."""
    from PIL import Image, ImageDraw

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # background circle — dark purple
    draw.ellipse([20, 20, size - 20, size - 20], fill=(30, 20, 50, 255))

    # mic body — trapezoid shape
    cx, cy = size // 2, size // 2 - 5
    mic_w, mic_h = 36, 70
    draw.rounded_rectangle(
        [cx - mic_w, cy - mic_h, cx + mic_w, cy + mic_h],
        radius=18,
        fill=(200, 50, 60, 255),
    )

    # mic stand
    draw.rectangle([cx - 8, cy + mic_h, cx + 8, cy + mic_h + 30], fill=(200, 50, 60, 255))
    draw.rectangle([cx - 30, cy + mic_h + 28, cx + 30, cy + mic_h + 36], fill=(200, 50, 60, 255))

    # sound waves
    for i, r in enumerate([80, 100, 120]):
        alpha = 180 - i * 50
        draw.arc(
            [cx - r, cy - r, cx + r, cy + r],
            start=-50, end=50,
            fill=(100, 180, 140, alpha),
            width=6,
        )

    # sparkle
    draw.ellipse([cx + 50, cy - 75, cx + 70, cy - 55], fill=(255, 220, 60, 230))
    draw.ellipse([cx - 70, cy - 70, cx - 50, cy - 50], fill=(255, 220, 60, 200))

    ico_path = os.path.join(HERE, "icon.ico")
    img.save(ico_path, format="ICO", sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"[build] Icon created: {ico_path}")
    return ico_path

# ── Step 2: PyInstaller ────────────────────────────────────────────
def build_exe(ico_path):
    print("[build] Running PyInstaller...")
    spec = f"""# -*- mode: python -*-
a = Analysis(
    ['{os.path.join(HERE, 'main.py')}'],
    pathex=['{HERE}'],
    binaries=[],
    datas=[],
    hiddenimports=['vosk', 'sounddevice', 'pynput', 'pyperclip', 'numpy', 'tkinter'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['{ico_path}'],
)
"""
    spec_path = os.path.join(HERE, f"{APP_NAME}.spec")
    with open(spec_path, "w") as f:
        f.write(spec)

    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", spec_path],
        cwd=HERE,
    )
    print("[build] PyInstaller complete.")

# ── Step 3: Copy to Desktop ────────────────────────────────────────
def copy_to_desktop():
    src = os.path.join(HERE, "dist", f"{APP_NAME}.exe")
    dst = os.path.join(DESKTOP, f"{APP_NAME}.exe")
    shutil.copy2(src, dst)
    print(f"[build] Copied to Desktop: {dst}")
    return dst

# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"[build] Building {APP_NAME}...")
    # Ensure all deps
    deps = ["numpy", "pynput", "sounddevice", "vosk", "pyperclip", "pyinstaller", "Pillow"]
    for d in deps:
        subprocess.check_call([sys.executable, "-m", "pip", "install", d])
    print("[build] Dependencies OK.")

    ico = create_icon()
    build_exe(ico)
    result = copy_to_desktop()
    print(f"\n  {APP_NAME}.exe is on your desktop! Double-click to launch.")
