"""Icons of the repo's webs and bots: Be Water, Biwenger Tools, Chuck Norris Bot.

Same house style as the Android app icons (lillo-android-apps, scripts/icon_lib.py): flat shapes
on a dark vertical gradient, drawn 4x supersampled with Pillow and scaled down with LANCZOS.
Coordinates are in a 108x108 design space of which the window 18..90 is shown (the same window
as the apps' Play Store icon), so shapes centred at 54 sit in the middle.

The single source of these icons; jorgelillo7.github.io and the webs only hold its output.

  python3 scripts/generate_web_icons.py site <out_dir>
      <out_dir>/{be-water,biwenger-tools,chucknorris-bot}{,-512}.png, 192 and 512 px.
      The 192 px ones are the "Webs y bots" cards of jorgelillo7.github.io (assets/apps/);
      the 512 px Chuck is the bot's Telegram picture.
  python3 scripts/generate_web_icons.py biwenger-web
      The installable-app icons in packages/biwenger_tools/web/static/: icon-192, icon-512,
      apple-touch-icon (180) and icon-maskable-512, a wider window that keeps the artwork
      inside the maskable safe zone.

Needs Pillow. When redrawing one, keep the style and check it at 48 and 72 px beside the others.
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

CREAM, INK = "#F4F1EA", "#0F172A"
SIZE, SS = 512, 4                        # output px, supersampling
SITE = (18, 90)    # visible window of the design space, as the apps' Play Store icon
# Maskable: the artwork reaches ~30 units from the centre and the safe zone is a circle of 40 %
# of the width, so an 80-unit window keeps all of it inside.
MASKABLE = (14, 94)

REPO = Path(__file__).resolve().parent.parent
BIWENGER_STATIC = REPO / "packages" / "biwenger_tools" / "web" / "static"


def canvas(top, bottom, window):
    """Supersampled image with a vertical gradient; P(x, y) maps design units to pixels, k = px per unit."""
    lo, hi = window
    s = SIZE * SS
    k = s / (hi - lo)
    img = Image.new("RGB", (s, s))
    d = ImageDraw.Draw(img)
    a = tuple(int(top[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(bottom[i:i + 2], 16) for i in (1, 3, 5))
    for y in range(s):
        d.line([(0, y), (s, y)], fill=tuple(int(a[j] + (b[j] - a[j]) * y / s) for j in range(3)))
    return img, d, (lambda x, y: ((x - lo) * k, (y - lo) * k)), k


def circ(d, P, k, x, y, r, c):
    X, Y = P(x, y)
    d.ellipse([X - r * k, Y - r * k, X + r * k, Y + r * k], fill=c)


def rrect(d, P, k, x0, y0, x1, y1, r, c):
    d.rounded_rectangle([*P(x0, y0), *P(x1, y1)], radius=r * k, fill=c)


def chaikin(points, rounds=4, closed=True):
    """Corner cutting: a coarse polygon becomes a smooth curve."""
    for _ in range(rounds):
        out = []
        pairs = list(zip(points, points[1:] + points[:1])) if closed else list(zip(points, points[1:]))
        for (x0, y0), (x1, y1) in pairs:
            out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
        points = out
    return points


def drop(cx, cy, r):
    """Teardrop pointing up."""
    return [(cx + r * math.sin(t) * math.sin(t / 2) * 1.05, cy - r * math.cos(t) * 1.25)
            for t in (i / 80 * math.tau for i in range(81))]


def ball(img, P, k, bx, by, br):
    """Football: a centre pentagon, five clipped rim pentagons and thin seams, clipped to a circle."""
    s = img.size[0]
    layer = Image.new("RGB", (s, s), CREAM)
    bd = ImageDraw.Draw(layer)

    def pent(cx, cy, r, rot):
        return [P(cx + r * math.cos(math.radians(rot + i * 72)), cy + r * math.sin(math.radians(rot + i * 72))) for i in range(5)]

    f = br / 8.5
    bd.polygon(pent(bx, by, 3.2 * f, -90), fill=INK)
    for i in range(5):
        m = math.radians(-54 + i * 72)
        bd.polygon(pent(bx + 9.0 * f * math.cos(m), by + 9.0 * f * math.sin(m), 3.0 * f, 126 + i * 72), fill=INK)
        v = math.radians(-90 + i * 72)
        bd.line([P(bx + 3.2 * f * math.cos(v), by + 3.2 * f * math.sin(v)),
                 P(bx + 6.4 * f * math.cos(v), by + 6.4 * f * math.sin(v))], fill=INK, width=int(0.5 * f * k))
    mask = Image.new("L", (s, s), 0)
    X, Y = P(bx, by)
    ImageDraw.Draw(mask).ellipse([X - br * k, Y - br * k, X + br * k, Y + br * k], fill=255)
    img.paste(layer, (0, 0), mask)
    ImageDraw.Draw(img).ellipse([X - br * k, Y - br * k, X + br * k, Y + br * k], outline=INK, width=int(0.6 * k))


def be_water(window=SITE):
    """A bottle of water (the catalogue of Spanish bottled waters): cap, two-tone water, label with a drop."""
    img, d, P, k = canvas("#0E5A8A", "#062338", window)
    shape = Image.new("L", img.size, 0)
    sd = ImageDraw.Draw(shape)
    sd.rounded_rectangle([*P(43, 40), *P(65, 83)], radius=4.5 * k, fill=255)
    sd.rectangle([*P(43, 40.5), *P(65, 60)], fill=255)
    sd.polygon([P(*p) for p in chaikin([(43, 47), (43, 39), (49, 32), (49, 29), (59, 29), (59, 32), (65, 39), (65, 47)], 3)], fill=255)
    img.paste(Image.new("RGB", img.size, "#BFE6FB"), (0, 0), shape)                       # empty part
    level = Image.new("L", img.size, 0)
    ImageDraw.Draw(level).rectangle([0, P(0, 48)[1], img.size[0], img.size[1]], fill=255)
    img.paste(Image.new("RGB", img.size, "#38BDF8"), (0, 0), ImageChops.multiply(shape, level))  # water
    d = ImageDraw.Draw(img)
    rrect(d, P, k, 47.5, 23, 60.5, 29.5, 1.4, CREAM)                                    # cap
    d.rectangle([*P(43, 56), *P(65, 70)], fill=CREAM)                                   # label
    d.polygon([P(*p) for p in drop(54, 63.2, 4.3)], fill="#0E7FC0")
    rrect(d, P, k, 46, 43, 48.2, 52, 1.1, "#E0F2FE")                                    # shine
    return img


def biwenger_tools(window=SITE):
    """The league's trophy (palmarés) with a football on top."""
    img, d, P, k = canvas("#166534", "#052E16", window)
    gold = "#FACC15"
    d.polygon([P(*p) for p in chaikin([(40, 46), (68, 46), (66, 60), (60, 66), (48, 66), (42, 60)], 3)], fill=gold)
    d.arc([*P(33.5, 47.5), *P(44, 59)], 90, 270, fill=gold, width=int(2.6 * k))     # handles
    d.arc([*P(64, 47.5), *P(74.5, 59)], 270, 450, fill=gold, width=int(2.6 * k))
    rrect(d, P, k, 51, 65, 57, 72, 0.5, gold)                                        # stem
    rrect(d, P, k, 44, 72, 64, 77, 1.5, gold)                                        # base
    rrect(d, P, k, 41, 77, 67, 81, 1.5, "#CA8A04")
    ball(img, P, k, 54, 36, 9.5)
    return img


def chucknorris_bot(window=SITE):
    """Chuck in his Walker, Texas Ranger hat: feathered hair, full beard, squint; a chat badge = bot."""
    img, d, P, k = canvas("#991B1B", "#3B0A0A", window)
    skin, hair, beard, hat = "#E6B08A", "#8A4B22", "#7A3E1A", "#C8A26B"
    d.polygon([P(*p) for p in chaikin([(30, 84), (32, 74), (44, 69), (64, 69), (76, 74), (78, 84)], 2)], fill="#3B5B92")  # denim shirt
    d.polygon([P(48, 69), P(54, 76), P(60, 69)], fill=skin)                                                               # neck
    d.polygon([P(*p) for p in chaikin([(40, 40), (68, 40), (69, 55), (66, 64), (60, 70), (48, 70), (42, 64), (39, 55)], 3)], fill=skin)
    d.polygon([P(*p) for p in chaikin([(38, 52), (37, 40), (42, 31), (54, 28), (66, 31), (71, 40), (70, 52), (67, 44),
                                        (60, 40), (50, 39), (42, 43)], 3)], fill=hair)
    d.polygon([P(*p) for p in chaikin([(39, 52), (42, 58), (47, 58), (54, 57), (61, 58), (66, 58), (69, 52), (70, 60),
                                        (66, 69), (58, 74), (50, 74), (42, 69), (38, 60)], 3)], fill=beard)
    d.polygon([P(*p) for p in chaikin([(46, 59.5), (50, 56.5), (54, 57.5), (58, 56.5), (62, 59.5), (58, 60.5), (54, 59.5),
                                        (50, 60.5)], 2)], fill="#6B3415")                                                   # moustache
    rrect(d, P, k, 51, 61, 57, 63, 0.8, "#5A1F0E")                                                                         # mouth
    for ex, s in ((48, 1), (60, -1)):                                                                                       # squint + frown
        d.line([P(ex - 3, 49), P(ex + 3, 49)], fill="#2A1A10", width=int(1.3 * k))
        d.line([P(ex - 3.6, 45.6 + (0.0 if s > 0 else 1.6)), P(ex + 3.6, 45.6 + (1.6 if s > 0 else 0.0))], fill="#5A2E12", width=int(1.9 * k))
    d.polygon([P(*p) for p in chaikin([(26, 38), (36, 35), (54, 34), (72, 35), (82, 38), (74, 41), (54, 40), (34, 41)], 3)], fill=hat)  # brim
    d.polygon([P(*p) for p in chaikin([(39, 36), (41, 24), (48, 20), (54, 23), (60, 20), (67, 24), (69, 36)], 3)], fill=hat)            # crown
    d.polygon([P(39.5, 33), P(68.5, 33), P(68.8, 36), P(39.2, 36)], fill="#6B4A26")                                                    # band
    rrect(d, P, k, 66, 64, 82, 76, 3, CREAM)                                                                               # chat badge
    d.polygon([P(70, 75.5), P(74, 75.5), P(68, 80)], fill=CREAM)
    for x in (70, 74, 78):
        circ(d, P, k, x, 70, 1.2, "#991B1B")
    return img


def render(make, size, window=SITE):
    """Draw at SIZE, then reduce — the 192 px cards are downsampled from the 512 px icon."""
    icon = make(window).resize((SIZE, SIZE), Image.LANCZOS)
    return icon if size == SIZE else icon.resize((size, size), Image.LANCZOS)


def site(out):
    out.mkdir(parents=True, exist_ok=True)
    for name, make in (("be-water", be_water), ("biwenger-tools", biwenger_tools),
                       ("chucknorris-bot", chucknorris_bot)):
        render(make, SIZE).save(out / f"{name}-512.png", optimize=True)
        render(make, 192).save(out / f"{name}.png", optimize=True)
        print("wrote", out / name)


def biwenger_web():
    for name, size, window in (("icon-192.png", 192, SITE), ("icon-512.png", 512, SITE),
                               ("apple-touch-icon.png", 180, SITE),
                               ("icon-maskable-512.png", 512, MASKABLE)):
        render(biwenger_tools, size, window).save(BIWENGER_STATIC / name, optimize=True)
        print("wrote", BIWENGER_STATIC / name)


if __name__ == "__main__":
    if sys.argv[1:2] == ["site"] and len(sys.argv) == 3:
        site(Path(sys.argv[2]))
    elif sys.argv[1:] == ["biwenger-web"]:
        biwenger_web()
    else:
        sys.exit(__doc__)
