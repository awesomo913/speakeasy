"""Dev tool: capture README screenshots of SpeakEasy's GUI surfaces.

Opens the settings window, every overlay state, the status dot in every
color, and renders the tray icons — then screenshots each and exits on its
own. Runs against a temporary APPDATA/LOCALAPPDATA so it shows fresh defaults
and never touches (or overwrites) the user's real settings.json.

THIS SCRIPT OPENS VISIBLE WINDOWS. Never run it in tests or CI.

Usage:  .venv-build\\Scripts\\python.exe scripts\\screenshot_ui.py [out_dir]
(out_dir defaults to ./screenshots)

Everything that touches a window, the filesystem outside this file, or
process-wide state (DPI awareness, APPDATA) lives inside main(), guarded by
the __main__ check below — importing this module (e.g. an import-smoke test)
has no side effects.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BACKDROP_BG = "#0f0f17"
DOT_LABEL_COLOR = "#8a8aa3"


def _out_dir() -> str:
    return sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "screenshots")


def main() -> None:  # noqa: PLR0915 — a linear screenshot script, not app logic
    import ctypes
    import tempfile
    import tkinter as tk

    # Must happen before any window is created — without it, ImageGrab pixel
    # coordinates and Tk's own winfo_root{x,y}/width/height disagree on a
    # scaled (>100%) display, and every crop lands in the wrong place.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except OSError as exc:
        print(f"[screenshot_ui] SetProcessDpiAwareness failed (continuing): {exc}")

    tmp_home = tempfile.mkdtemp(prefix="speakeasy_screenshot_")
    os.environ["APPDATA"] = tmp_home
    os.environ["LOCALAPPDATA"] = tmp_home

    from PIL import Image, ImageDraw, ImageFont, ImageGrab

    import settings_window
    import status_dot as _status_dot_module
    from overlay import Overlay
    from settings_window import open_settings_window
    from status_dot import StatusDot
    from theme import (
        COLOR_ERROR,
        COLOR_IDLE,
        COLOR_PASTING,
        COLOR_PAUSED,
        COLOR_RECORDING,
        COLOR_TRANSCRIBING,
    )
    from tray import _make_icon_image

    out_dir = _out_dir()
    os.makedirs(out_dir, exist_ok=True)

    overlay = Overlay()
    root = overlay.get_root()

    def _save(img, name: str) -> None:
        path = os.path.join(out_dir, name)
        img.save(path, format="PNG")
        print(f"[screenshot_ui] saved {path}")

    def _grab_widget(widget: tk.Misc):
        widget.update_idletasks()
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        w, h = widget.winfo_width(), widget.winfo_height()
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)

    def _grab_bbox(x: int, y: int, w: int, h: int):
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)

    def _backdrop(x: int, y: int, w: int, h: int) -> tk.Toplevel:
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.configure(bg=BACKDROP_BG)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.update_idletasks()
        return win

    steps: list = []

    def _run_next() -> None:
        if steps:
            steps.pop(0)()
        else:
            root.after(50, root.destroy)

    # ── Settings window ──────────────────────────────────────────────
    def step_settings() -> None:
        open_settings_window(root)

        def after_open() -> None:
            win = settings_window._win  # noqa: SLF001 — dev tool, reading the live Toplevel
            if win is not None:
                _save(_grab_widget(win), "settings.png")
                win.destroy()
            else:
                print("[screenshot_ui] settings window did not open; skipping settings.png")
            root.after(150, _run_next)

        root.after(300, after_open)

    # ── Overlay states ───────────────────────────────────────────────
    def _overlay_step(name: str, show_fn) -> None:
        bx, by, bw, bh = 200, 200, 320, 140
        backdrop = _backdrop(bx, by, bw, bh)
        near_x = bx + bw // 2
        near_y = by + bh // 2 + Overlay.HEIGHT // 2 + 24
        show_fn(near_x, near_y)

        def after_show() -> None:
            _save(_grab_bbox(bx, by, bw, bh), name)
            overlay.hide()
            backdrop.destroy()
            root.after(100, _run_next)

        root.after(300, after_show)

    def step_overlay_recording() -> None:
        _overlay_step("overlay_recording.png", overlay.state_recording)

    def step_overlay_transcribing() -> None:
        _overlay_step("overlay_transcribing.png", overlay.state_transcribing)

    def step_overlay_pasted() -> None:
        preview = "Quick update: the build is green."
        _overlay_step(
            "overlay_pasted.png",
            lambda x, y: overlay.state_pasting(preview, x, y),
        )

    # ── Status dot, every color, one combined strip ─────────────────
    def step_dot_states() -> None:
        size = _status_dot_module.SIZE
        colors = [
            ("Idle", COLOR_IDLE),
            ("Recording", COLOR_RECORDING),
            ("Transcribing", COLOR_TRANSCRIBING),
            ("Pasting", COLOR_PASTING),
            ("Paused", COLOR_PAUSED),
            ("Error", COLOR_ERROR),
        ]
        # Tile width is driven by the longest label ("Transcribing"), not the
        # tiny dot, so labels never bleed into their neighbor.
        label_font = ImageFont.load_default()
        label_w = max(
            ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(label, font=label_font)
            for label, _color in colors
        )
        pad = 20
        tile = int(label_w) + 24
        bw = pad * 2 + tile * len(colors)
        bh = pad * 2 + size + 20
        bx, by = 200, 200
        backdrop = _backdrop(bx, by, bw, bh)

        dot = StatusDot(root, on_toggle_pause=lambda: None)
        dot.show()
        dot_x, dot_y = bx + pad, by + pad
        dot._win.overrideredirect(True)  # noqa: SLF001 — dev tool, positioning for capture
        dot._win.geometry(f"{size}x{size}+{dot_x}+{dot_y}")  # noqa: SLF001

        combined = Image.new("RGB", (bw, bh), BACKDROP_BG)
        draw = ImageDraw.Draw(combined)
        index = {"i": 0}

        def capture_next() -> None:
            i = index["i"]
            if i >= len(colors):
                dot.destroy()
                backdrop.destroy()
                _save(combined, "dot_states.png")
                root.after(100, _run_next)
                return
            label, color = colors[i]
            dot._set(color, pulse=False)  # noqa: SLF001 — dev tool, no pulse animation needed

            def after_draw() -> None:
                crop = _grab_bbox(dot_x, dot_y, size, size)
                tile_x = pad + i * tile
                dot_center = tile_x + label_w / 2
                combined.paste(crop, (int(dot_center - size / 2), pad))
                text_w = draw.textlength(label, font=label_font)
                draw.text(
                    (dot_center - text_w / 2, pad + size + 4), label,
                    fill=DOT_LABEL_COLOR, font=label_font,
                )
                index["i"] += 1
                root.after(80, capture_next)

            root.after(150, after_draw)

        capture_next()

    # ── Tray icons — pure PIL, no window needed ──────────────────────
    def step_tray_icons() -> None:
        normal = _make_icon_image(paused=False).resize((128, 128), Image.LANCZOS)
        paused = _make_icon_image(paused=True).resize((128, 128), Image.LANCZOS)
        _save(normal, "tray_icon.png")
        _save(paused, "tray_icon_paused.png")
        root.after(10, _run_next)

    steps.extend([
        step_settings,
        step_overlay_recording,
        step_overlay_transcribing,
        step_overlay_pasted,
        step_dot_states,
        step_tray_icons,
    ])
    _run_next()
    root.mainloop()


if __name__ == "__main__":
    main()
