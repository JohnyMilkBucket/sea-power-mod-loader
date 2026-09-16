"""Generate the app icon and small UI logo from the approved master mark."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icon.ico"
SOURCE = ROOT / "assets" / "logo-modern-dark-minimal-stack.png"
PREVIEW = ROOT / "assets" / "icon-preview.png"
UI_LOGO = ROOT / "assets" / "logo-ui.png"

NAVY = (14, 30, 48, 255)
NAVY_EDGE = (28, 56, 84, 255)
SWEEP = (46, 120, 110, 255)
LAYERS = [(86, 214, 168, 255), (60, 176, 200, 255), (44, 118, 176, 255)]
SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size: int) -> Image.Image:
    """Place the transparent mark on a dark tile that survives tiny icon sizes."""
    scale = 8 if size <= 64 else 2
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22),
                        fill=NAVY, outline=NAVY_EDGE, width=max(1, int(s * 0.02)))
    mark = Image.open(SOURCE).convert("RGBA")
    mark.thumbnail((int(s * 0.84), int(s * 0.84)), Image.Resampling.LANCZOS)
    image.alpha_composite(mark, ((s - mark.width) // 2, (s - mark.height) // 2))
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw(size) for size in SIZES]
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, sizes {SIZES})")

    frames[-1].save(PREVIEW)
    print(f"wrote {PREVIEW}")

    mark = Image.open(SOURCE).convert("RGBA")
    mark.thumbnail((40, 40), Image.Resampling.LANCZOS)
    mark.save(UI_LOGO)
    print(f"wrote {UI_LOGO}")


if __name__ == "__main__":
    main()
