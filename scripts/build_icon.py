"""Generate assets/vibeparser.ico used by the Windows executable."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SIZE = 512
TOP = (9, 14, 26)
BOTTOM = (17, 27, 48)
ACCENT = (59, 130, 246)
GREEN = (74, 222, 128)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        for folder in (
            Path("C:/Windows/Fonts"),
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/Library/Fonts"),
        ):
            candidate = folder / name
            if candidate.exists():
                try:
                    return ImageFont.truetype(str(candidate), size=size)
                except OSError:
                    continue
    return ImageFont.load_default(size=size)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Rounded gradient tile.
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=112, fill=255)
    gradient = Image.new("RGB", (SIZE, SIZE), TOP)
    grad_draw = ImageDraw.Draw(gradient)
    for y in range(SIZE):
        ratio = y / (SIZE - 1)
        color = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * ratio) for i in range(3))
        grad_draw.line([(0, y), (SIZE, y)], fill=color)
    image.paste(gradient, (0, 0), mask)

    # Accent top bar.
    draw.rounded_rectangle([8, 8, SIZE - 8, 34], radius=13, fill=ACCENT)

    # "VP" monogram.
    font = _font(230)
    text = "VP"
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.text(
        ((SIZE - tw) / 2 - box[0], (SIZE - th) / 2 - box[1] - 18),
        text,
        font=font,
        fill=(240, 244, 255),
    )

    # Green "new order" dot.
    draw.ellipse([SIZE - 132, SIZE - 132, SIZE - 60, SIZE - 60], fill=GREEN)

    out = ASSETS / "vibeparser.ico"
    image.save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"icon: {out}")


if __name__ == "__main__":
    sys.exit(main())
