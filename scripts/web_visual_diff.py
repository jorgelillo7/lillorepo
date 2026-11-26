#!/usr/bin/env python3
"""Pixel-compare the same pages on two servers: before and after a CSS change.

    python3 scripts/web_visual_diff.py BEFORE_URL AFTER_URL /path /other/path \\
        [--widths 320,390,1440] [--scheme light|dark] [--out DIR]

Screenshots each path at each width (3000 px tall) on both servers — typically
`master` from a git worktree and the branch, both run locally against the same
data — and prints SAME, or DIFF with the changed pixel count and bounding box.
With `--out`, writes each pair and a mask of the changed pixels there. Exits 1
when any page differs, so a refactor that should change nothing can be gated on
it. Photos still lazy-loading differ between runs; look at the box before
blaming the CSS.

Needs Playwright and Pillow, outside the lock on purpose:
    pip3 install playwright pillow && python3 -m playwright install chromium
"""

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright


def shoot(page, url: str) -> Image.Image:
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(1500)
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--widths", default="320,390,1440")
    parser.add_argument("--scheme", choices=("light", "dark"), default="light")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)

    same = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width in (int(w) for w in args.widths.split(",")):
            context = browser.new_context(
                viewport={"width": width, "height": 3000},
                is_mobile=width < 800,
                color_scheme=args.scheme,
            )
            page = context.new_page()
            for path in args.paths:
                before = shoot(page, args.before.rstrip("/") + path)
                after = shoot(page, args.after.rstrip("/") + path)
                diff = ImageChops.difference(before, after)
                box = diff.getbbox()
                name = f"{path.strip('/').replace('/', '_') or 'home'}-{width}"
                if box:
                    same = False
                    changed = sum(1 for px in diff.get_flattened_data() if px != (0, 0, 0))
                    print(f"DIFF {name}: {changed} px in {box}")
                    if args.out:
                        before.save(args.out / f"{name}-before.png")
                        after.save(args.out / f"{name}-after.png")
                        diff.point(lambda v: 255 if v else 0).save(args.out / f"{name}-mask.png")
                else:
                    print(f"SAME {name}")
            context.close()
        browser.close()
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
