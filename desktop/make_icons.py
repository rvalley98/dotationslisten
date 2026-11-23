"""App icons drawn with Pillow - no external assets.

    python desktop/make_icons.py <build dir>

macOS: Dotationslisten.icns + menu bar template PNGs; Windows: Dotationslisten.ico + tray.png.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

RED = (200, 16, 46, 255)
WHITE = (255, 255, 255, 255)


def app_icon(size: int) -> Image.Image:
    s = size / 1024
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((100 * s, 100 * s, 924 * s, 924 * s), radius=185 * s, fill=RED)
    # sheet of paper with list lines and a check mark
    d.rounded_rectangle((270 * s, 190 * s, 754 * s, 834 * s), radius=40 * s, fill=WHITE)
    for i, y in enumerate((330, 440, 550, 660)):
        d.rounded_rectangle((330 * s, (y - 18) * s, (560 if i % 2 else 620) * s, (y + 18) * s), radius=18 * s, fill=RED)
    d.line(((590 * s, 640 * s), (640 * s, 700 * s), (720 * s, 560 * s)), fill=RED, width=max(1, int(42 * s)), joint="curve")
    return im


def menubar_icon(size: int) -> Image.Image:
    """Black on transparent; macOS tints template images for light/dark menu bars."""
    s = size / 22
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((4 * s, 2 * s, 18 * s, 20 * s), radius=2 * s, outline=(0, 0, 0, 255), width=max(1, int(1.6 * s)))
    for y in (7, 11, 15):
        d.line((7 * s, y * s, 15 * s, y * s), fill=(0, 0, 0, 255), width=max(1, int(1.6 * s)))
    return im


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    big = app_icon(1024)
    big.save(out / "Dotationslisten.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    app_icon(64).save(out / "tray.png")
    if not shutil.which("iconutil"):  # Windows/Linux: no .icns needed
        return
    iconset = out / "Dotationslisten.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    iconset.mkdir()
    for px in (16, 32, 128, 256, 512):
        app_icon(px).save(iconset / f"icon_{px}x{px}.png")
        app_icon(px * 2).save(iconset / f"icon_{px}x{px}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out / "Dotationslisten.icns")], check=True)
    shutil.rmtree(iconset)
    menubar_icon(22).save(out / "menubar.png")
    menubar_icon(44).save(out / "menubar@2x.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
