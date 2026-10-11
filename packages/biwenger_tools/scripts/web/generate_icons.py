"""Generate the web's home-screen and install icons from one geometry definition.

A gold trophy with a ball on a dark green gradient — the icon the personal site
(jorgelillo7.github.io) shows for this project, in the flat style of the
Android apps. Coordinates are in a 192x192 grid, drawn at 4x and downsampled.

Writes into packages/biwenger_tools/web/static/:

  icon-192.png, icon-512.png    manifest icons ("any")
  icon-maskable-512.png         artwork shrunk into the maskable safe zone
  apple-touch-icon.png          180 px, iPhone home screen

Usage (repo root): python3 packages/biwenger_tools/scripts/web/generate_icons.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

STATIC = Path(__file__).resolve().parents[2] / "web" / "static"

TOP, BOTTOM = (0x15, 0x63, 0x33), (0x05, 0x2F, 0x16)
GOLD, GOLD_DARK = (0xFA, 0xCC, 0x15), (0xCA, 0x8A, 0x04)
WHITE, INK = (0xF4, 0xF1, 0xEA), (0x0F, 0x17, 0x2A)

BALL_X, BALL_Y, BALL_R = 96, 44, 25
SUPERSAMPLE = 4

# name, size in px, artwork scale (the maskable safe zone is the inner 80 %)
ICONS = [
    ("icon-192.png", 192, 1.0),
    ("icon-512.png", 512, 1.0),
    ("icon-maskable-512.png", 512, 0.72),
    ("apple-touch-icon.png", 180, 1.0),
]


def render(size: int, scale: float) -> Image.Image:
    n = size * SUPERSAMPLE
    img = Image.new("RGB", (n, n))
    d = ImageDraw.Draw(img)
    for y in range(n):
        t = y / (n - 1)
        colour = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))
        d.line([(0, y), (n, y)], fill=colour)

    k = n / 192 * scale
    off = n / 2 - 96 * k

    def p(x: float, y: float) -> tuple[float, float]:
        return (off + x * k, off + y * k)

    def box(x0: float, y0: float, x1: float, y1: float) -> list:
        return [p(x0, y0), p(x1, y1)]

    _trophy(d, p, box, k)
    _ball(img, d, p, box, k, n)
    return img.resize((size, size), Image.LANCZOS)


def _trophy(d: ImageDraw.ImageDraw, p, box, k: float) -> None:
    d.arc(box(40, 82, 68, 114), 90, 270, fill=GOLD, width=round(7 * k))
    d.arc(box(124, 82, 152, 114), -90, 90, fill=GOLD, width=round(7 * k))
    bowl = [p(60, 76), p(132, 76)]
    bowl += [
        p(96 + 35 * math.cos(math.radians(i)), 92 + 30 * math.sin(math.radians(i)))
        for i in range(181)
    ]
    d.polygon(bowl, fill=GOLD)
    d.rectangle(box(61, 76, 131, 92), fill=GOLD)
    d.polygon([p(89, 118), p(103, 118), p(101, 146), p(91, 146)], fill=GOLD)
    d.rounded_rectangle(box(78, 144, 114, 152), radius=2 * k, fill=GOLD)
    d.rounded_rectangle(box(62, 152, 130, 161), radius=3 * k, fill=GOLD_DARK)


def _ball(img: Image.Image, d: ImageDraw.ImageDraw, p, box, k: float, n: int) -> None:
    cx, cy, r = BALL_X, BALL_Y, BALL_R
    d.ellipse(box(cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), fill=INK)

    # Panels are drawn on their own layer and clipped to the ball, so the edge
    # pentagons are cut by its outline instead of spilling past it.
    ball = Image.new("RGB", (n, n), WHITE)
    b = ImageDraw.Draw(ball)

    def pentagon(px: float, py: float, rad: float, rot: float) -> list:
        return [
            p(
                px + rad * math.cos(math.radians(rot + 72 * j)),
                py + rad * math.sin(math.radians(rot + 72 * j)),
            )
            for j in range(5)
        ]

    def towards(rad: float, deg: float) -> tuple[float, float]:
        return p(
            cx + rad * math.cos(math.radians(deg)),
            cy + rad * math.sin(math.radians(deg)),
        )

    seam = round(1.6 * k)
    b.polygon(pentagon(cx, cy, 9, -90), fill=INK)
    for j in range(5):
        edge = -54 + 72 * j
        b.polygon(
            pentagon(
                cx + 25 * math.cos(math.radians(edge)),
                cy + 25 * math.sin(math.radians(edge)),
                9,
                edge + 180,
            ),
            fill=INK,
        )
        corner = -90 + 72 * j
        b.line([towards(10, corner), towards(19, corner + 36)], fill=INK, width=seam)
        b.line([towards(10, corner), towards(19, corner - 36)], fill=INK, width=seam)

    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).ellipse(box(cx - r, cy - r, cx + r, cy + r), fill=255)
    img.paste(ball, (0, 0), mask)


def main() -> None:
    for name, size, scale in ICONS:
        render(size, scale).save(STATIC / name, optimize=True)
        print(f"wrote {STATIC / name}")


if __name__ == "__main__":
    main()
