"""Step 1: Generate icon only."""
from PIL import Image, ImageDraw
import os

HERE = os.path.dirname(os.path.abspath(__file__))
size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# background circle — dark purple
draw.ellipse([20, 20, size - 20, size - 20], fill=(30, 20, 50, 255))

# mic body
cx, cy = size // 2, size // 2 - 5
mic_w, mic_h = 36, 70
draw.rounded_rectangle(
    [cx - mic_w, cy - mic_h, cx + mic_w, cy + mic_h],
    radius=18, fill=(200, 50, 60, 255),
)
# stand
draw.rectangle([cx - 8, cy + mic_h, cx + 8, cy + mic_h + 30], fill=(200, 50, 60, 255))
draw.rectangle([cx - 30, cy + mic_h + 28, cx + 30, cy + mic_h + 36], fill=(200, 50, 60, 255))

# sound waves
for i, r in enumerate([80, 100, 120]):
    alpha = 180 - i * 50
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=-50, end=50, fill=(100, 180, 140, alpha), width=6)

# sparkles
draw.ellipse([cx + 50, cy - 75, cx + 70, cy - 55], fill=(255, 220, 60, 230))
draw.ellipse([cx - 70, cy - 70, cx - 50, cy - 50], fill=(255, 220, 60, 200))

ico_path = os.path.join(HERE, "icon.ico")
img.save(ico_path, format="ICO", sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
print(f"Icon created: {ico_path}")
