"""Shared icon artwork — one drawing function used by tray.py (live tray
icons) and scripts/make_icon.py (icon.ico + docs/assets/icon-256.png), so the
two can never drift into two different mic-glyph shapes.

Always draw at RENDER_SIZE and let the caller downscale with LANCZOS — that's
what keeps edges smooth at the small sizes a tray icon actually renders at.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

RENDER_SIZE = 512

# Paused variant: desaturated grey gradient (top-left -> bottom-right), same
# shape as the normal icon. Not in theme.py because nothing else needs it.
PAUSED_TOP = "#6b6b80"
PAUSED_BOTTOM = "#4a4a5c"

_ICON_BG = (20, 20, 31, 255)  # matches theme.BG, used for the badge outline


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _gradient_tile(size: int, top_hex: str, bottom_hex: str) -> Image.Image:
    """Diagonal top -> bottom gradient, clipped to a rounded-square tile."""
    top = _hex_to_rgb(top_hex)
    bottom = _hex_to_rgb(bottom_hex)
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    for y in range(size):
        t = y / (size - 1)
        row = (
            _lerp(top[0], bottom[0], t),
            _lerp(top[1], bottom[1], t),
            _lerp(top[2], bottom[2], t),
        )
        for x in range(size):
            px[x, y] = row

    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    pad = int(size * 0.03)
    mdraw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=radius, fill=255)

    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base.paste(grad, (0, 0), mask)
    return base


def _draw_mic(img: Image.Image) -> None:
    """Capsule body + U-shaped stand arc + short stem, all in white."""
    size = img.size[0]
    draw = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)

    cx = size // 2
    cy = int(size * 0.42)
    mic_w, mic_h = int(size * 0.13), int(size * 0.19)

    # capsule (mic body)
    draw.rounded_rectangle(
        [cx - mic_w, cy - mic_h, cx + mic_w, cy + mic_h],
        radius=mic_w, fill=white,
    )

    # U-shaped stand arc cradling the capsule from below (open at the top).
    # PIL's arc() sweeps angles clockwise in this y-down space, where 0=right,
    # 90=bottom, 180=left — so 340->200 traces right-to-bottom-to-left (the
    # bottom half of the circle, with a small hook past horizontal on each
    # side), which is the U shape. 160->380 (what a naive "U" guess picks)
    # instead traces the TOP half — a dome that reads as ears, not a stand.
    arc_r = int(mic_w * 1.5)
    arc_cy = cy + int(mic_h * 0.55)
    stroke = max(2, int(size * 0.028))
    draw.arc(
        [cx - arc_r, arc_cy - arc_r, cx + arc_r, arc_cy + arc_r],
        start=340, end=200, fill=white, width=stroke,
    )

    # short stem down from the arc, plus a small base
    stem_top = arc_cy + arc_r - int(stroke * 0.4)
    stem_bottom = stem_top + int(size * 0.09)
    stem_w = max(2, int(size * 0.018))
    draw.rectangle([cx - stem_w, stem_top, cx + stem_w, stem_bottom], fill=white)

    base_w = int(size * 0.08)
    base_h = int(size * 0.022)
    draw.rounded_rectangle(
        [cx - base_w, stem_bottom, cx + base_w, stem_bottom + base_h],
        radius=base_h, fill=white,
    )


def build_icon(top_hex: str, bottom_hex: str, render_size: int = RENDER_SIZE) -> Image.Image:
    """Rounded-square gradient tile with the white mic glyph, at render_size."""
    img = _gradient_tile(render_size, top_hex, bottom_hex)
    _draw_mic(img)
    return img


def build_icon_with_badge(
    top_hex: str, bottom_hex: str, badge_hex: str, render_size: int = RENDER_SIZE,
) -> Image.Image:
    """The normal icon plus a small badge dot, bottom-right, with a dark outline."""
    img = build_icon(top_hex, bottom_hex, render_size)
    draw = ImageDraw.Draw(img)
    r = int(render_size * 0.15)
    margin = int(render_size * 0.06)
    cx = render_size - margin - r
    cy = render_size - margin - r
    outline_w = max(2, int(render_size * 0.02))
    draw.ellipse(
        [cx - r - outline_w, cy - r - outline_w, cx + r + outline_w, cy + r + outline_w],
        fill=_ICON_BG,
    )
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_hex_to_rgb(badge_hex) + (255,))
    return img
