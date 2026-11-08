"""Cut a character out of a scene's picture, for the 3D draft's `figures`.

    python3 cutout.py <picture> <empty-room> <green-matte> <out.png>
                      [--dark-box x0,y0,x1,y1] [--single]
                      [--exclude x0,y0,x1,y1 ...] [--bw] [--diff-box x0,y0,x1,y1]
                      [--mask-only]

Needs numpy, scipy and pillow (a throwaway venv: `python3 -m venv /tmp/cut &&
/tmp/cut/bin/pip3 install numpy scipy pillow`). The two other pictures come
from `view.ts` edits of the original (see the scene-3d skill): the room with
the character removed, and the picture with everything but the character in
flat #00FF00. Prints the cut-out's `rect` in percent of the picture.

Two masks, because each fails somewhere: the difference with the empty room
says where the character is but misses dark parts against a dark background;
the green matte has a clean outline but may keep furniture. Inside
`--dark-box` (fractions of the picture: the boots, say) the matte alone
decides. `--single` keeps only the largest piece (a stray lamp or cable that
changed between the two pictures). `--exclude` (repeatable, fractions of the
picture) drops what is still attached to the character but not part of her.
`--bw` reads the matte as a black-and-white mask (character white) instead of
a green screen: Gemini paints such a mask faithfully where it leaves a green
screen half done. Inside `--diff-box` the difference alone decides (dark
trousers the mask missed). `--mask-only` ignores the difference: for an edit
that also relit the room, where the two pictures differ everywhere.
"""

import json
import sys

import numpy as np
from PIL import Image
from scipy import ndimage


def main() -> None:
    args = sys.argv[1:]
    box_frac = None
    mask_only = "--mask-only" in args
    if mask_only:
        args.remove("--mask-only")
    bw = "--bw" in args or mask_only
    if "--bw" in args:
        args.remove("--bw")
    diff_box = None
    if "--diff-box" in args:
        i = args.index("--diff-box")
        diff_box = [float(v) for v in args[i + 1].split(",")]
        del args[i : i + 2]
    excludes = []
    while "--exclude" in args:
        i = args.index("--exclude")
        excludes.append([float(v) for v in args[i + 1].split(",")])
        del args[i : i + 2]
    single = "--single" in args
    if single:
        args.remove("--single")
    if "--dark-box" in args:
        i = args.index("--dark-box")
        box_frac = [float(v) for v in args[i + 1].split(",")]
        del args[i : i + 2]
    orig, empty, green, out = args[:4]

    o = Image.open(orig).convert("RGB")
    width, height = o.size
    a = np.asarray(o, float)
    e = np.asarray(
        Image.open(empty).convert("RGB").resize(o.size, Image.LANCZOS), float
    )
    g = np.asarray(
        Image.open(green).convert("RGB").resize(o.size, Image.LANCZOS), float
    )

    # Where she is: the original against the room without her.
    d = ndimage.gaussian_filter(np.sqrt(((a - e) ** 2).sum(-1)), 2)
    m = ndimage.binary_opening(d > 38, iterations=2)
    lab, _ = ndimage.label(m)
    sizes = np.bincount(lab.ravel())[1:]
    order = np.argsort(sizes)[::-1]
    near = lab == order[0] + 1
    ys, xs = np.where(near)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    for i in order[1:15]:
        if sizes[i] < 1500:
            continue
        yy, xx = np.where(lab == i + 1)
        if (
            xx.min() > x0 - 150
            and xx.max() < x1 + 150
            and yy.min() > y0 - 150
            and yy.max() < y1 + 150
        ):
            near |= lab == i + 1
    near = ndimage.binary_closing(near, iterations=25)
    # A black-and-white mask is trusted for the outline: the difference only
    # bounds where to look, so far-off specks of the mask drop out.
    near = ndimage.binary_dilation(
        ndimage.binary_fill_holes(near), iterations=90 if bw else 30
    )

    # Her outline: the green matte.
    if bw:
        fg = g.mean(-1) > 128
    else:
        r, gg, b = g[..., 0], g[..., 1], g[..., 2]
        fg = ~((gg > 150) & (gg > r * 1.6) & (gg > b * 1.6))
    keep = ndimage.binary_opening(fg if mask_only else fg & near, iterations=2)
    lab, _ = ndimage.label(keep)
    sizes = np.bincount(lab.ravel())[1:]
    keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > 3000])
    keep = (
        ndimage.binary_fill_holes(keep) if bw else ndimage.binary_fill_holes(keep) & fg
    )

    if box_frac:
        bx0, by0, bx1, by1 = box_frac
        box = np.zeros_like(keep)
        box[
            int(height * by0) : int(height * by1), int(width * bx0) : int(width * bx1)
        ] = True
        dark = ndimage.binary_opening(fg & box, iterations=2)
        lab, _ = ndimage.label(dark | keep)
        main_label = np.bincount(lab[keep].ravel()).argmax()
        keep = (keep | dark) & (lab == main_label)

    if diff_box:
        dx0, dy0, dx1, dy1 = diff_box
        region = np.zeros_like(keep)
        region[
            int(height * dy0) : int(height * dy1), int(width * dx0) : int(width * dx1)
        ] = True
        keep |= region & ndimage.binary_opening(d > 30, iterations=2)

    for ex0, ey0, ex1, ey1 in excludes:
        keep[
            int(height * ey0) : int(height * ey1), int(width * ex0) : int(width * ex1)
        ] = False

    if single:
        lab, _ = ndimage.label(keep)
        keep = lab == np.bincount(lab[keep].ravel()).argmax()

    keep = ndimage.binary_erosion(keep, iterations=1)
    alpha = ndimage.gaussian_filter(keep.astype(float), 1.2)
    ys, xs = np.where(keep)
    pad = 6
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(width - 1, xs.max() + pad), min(height - 1, ys.max() + pad)
    rgba = np.dstack([a, alpha * 255]).astype("uint8")[y0 : y1 + 1, x0 : x1 + 1]
    Image.fromarray(rgba, "RGBA").save(out)
    rect = [
        x0 / width * 100,
        y0 / height * 100,
        (x1 - x0 + 1) / width * 100,
        (y1 - y0 + 1) / height * 100,
    ]
    print(json.dumps([round(v, 3) for v in rect]))


if __name__ == "__main__":
    main()
