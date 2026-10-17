"""Draw the integration icon (a stove with a flame) into custom_components/.../brand/.

Run with the test virtualenv, which has Pillow through Home Assistant:
    .venv/bin/python scripts/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024  # drawing size; scaled down with antialiasing
BRAND_DIR = Path(__file__).parent.parent / "custom_components" / "oven_control" / "brand"


def draw(body: str, window: str, outline: str) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = SIZE / 100

    def box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
        return [x0 * s, y0 * s, x1 * s, y1 * s]

    # Flue pipe and stove body.
    d.rounded_rectangle(box(41, 2, 59, 22), radius=2 * s, fill=body)
    d.rounded_rectangle(box(18, 18, 82, 92), radius=9 * s, fill=body)
    # Feet.
    d.rounded_rectangle(box(24, 88, 36, 98), radius=2 * s, fill=body)
    d.rounded_rectangle(box(64, 88, 76, 98), radius=2 * s, fill=body)
    # Window.
    d.rounded_rectangle(
        box(27, 30, 73, 80), radius=6 * s, fill=window, outline=outline, width=int(2.5 * s)
    )

    # Flame: outer and inner teardrop made of a circle and a triangle.
    def flame(cx: float, bottom: float, w: float, h: float, color: str) -> None:
        r = w / 2
        d.ellipse(box(cx - r, bottom - 2 * r, cx + r, bottom), fill=color)
        d.polygon(
            [
                ((cx - r * 0.98) * s, (bottom - r * 1.1) * s),
                ((cx + r * 0.98) * s, (bottom - r * 1.1) * s),
                ((cx + r * 0.25) * s, (bottom - h) * s),
            ],
            fill=color,
        )

    flame(50, 74, 28, 40, "#ff7a1a")
    flame(49, 74, 16, 25, "#ffd23f")
    # Logs.
    d.rounded_rectangle(box(32, 72, 68, 77), radius=2 * s, fill="#8a4b22")
    return img


def main() -> None:
    BRAND_DIR.mkdir(exist_ok=True)
    variants = {
        "": draw(body="#37474f", window="#263238", outline="#90a4ae"),
        "dark_": draw(body="#cfd8dc", window="#263238", outline="#90a4ae"),
    }
    for prefix, img in variants.items():
        img.resize((256, 256), Image.Resampling.LANCZOS).save(BRAND_DIR / f"{prefix}icon.png")
        img.resize((512, 512), Image.Resampling.LANCZOS).save(BRAND_DIR / f"{prefix}icon@2x.png")


if __name__ == "__main__":
    main()
