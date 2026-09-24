"""Generate SpeakEasy's app icon: a rounded-square teal->blue gradient tile
with a white microphone glyph (capsule + U-shaped stand arc + stem).

The actual drawing lives in icon_art.py, shared with tray.py so the live tray
icon and this shipped icon.ico can never drift apart. Renders at high
resolution then downscales with LANCZOS resampling for clean anti-aliased
edges, matching the theme.py palette (teal accent, blue "transcribing" color).

Outputs:
  - icon.ico              (project root; sizes 16-256, used by PyInstaller)
  - docs/assets/icon-256.png  (a flat PNG for READMEs / web use)

Run from the project root:  .venv-build\\Scripts\\python.exe scripts\\make_icon.py
"""
from __future__ import annotations

import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from icon_art import build_icon  # noqa: E402 — needs sys.path set first
from theme import ACCENT, TRANSCRIBING  # noqa: E402 — needs sys.path set first

RENDER_SIZE = 1024  # render big, downscale for anti-aliasing
ICO_SIZES = [256, 128, 64, 48, 32, 16]


def main() -> None:
    img = build_icon(ACCENT, TRANSCRIBING, RENDER_SIZE)

    ico_path = os.path.join(ROOT, "icon.ico")
    resized = [img.resize((s, s), Image.LANCZOS) for s in ICO_SIZES]
    resized[0].save(
        ico_path, format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=resized[1:],
    )
    print(f"[make_icon] wrote {ico_path}")

    png_dir = os.path.join(ROOT, "docs", "assets")
    os.makedirs(png_dir, exist_ok=True)
    png_path = os.path.join(png_dir, "icon-256.png")
    img.resize((256, 256), Image.LANCZOS).save(png_path, format="PNG")
    print(f"[make_icon] wrote {png_path}")


if __name__ == "__main__":
    main()
