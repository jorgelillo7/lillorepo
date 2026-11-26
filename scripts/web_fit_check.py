#!/usr/bin/env python3
"""Does a page's header fit every phone width, without anything reaching the edge?

    python3 scripts/web_fit_check.py URL [--selector nav] [--dark] [--margin 16]

Loads URL at 320, 360, 375, 390, 393, 402, 414 and 430 px (phone emulation) and
measures, inside `--selector` (default the first <nav>), the right edge of every
visible link, button, input and Google sign-in button. A width passes when that
edge stays `--margin` px inside the screen and the page never scrolls sideways.
Exits 1 when any width fails. Run it after adding anything to a header: a theme
button and Google's sign-in each pushed be_water's off the screen.

Needs Playwright, outside the lock on purpose:
    pip3 install playwright && python3 -m playwright install chromium
"""

import argparse
import sys

from playwright.sync_api import sync_playwright

WIDTHS = (320, 360, 375, 390, 393, 402, 414, 430)
MEASURE = """(selector) => {
  const root = document.querySelector(selector);
  if (!root) return null;
  const items = [...root.querySelectorAll('a, button, input, .g_id_signin')].filter((e) => e.offsetParent);
  const right = Math.max(0, ...items.map((e) => e.getBoundingClientRect().right));
  return { right: Math.round(right), scrollWidth: document.documentElement.scrollWidth };
}"""


def check(url: str, selector: str, dark: bool, margin: int) -> bool:
    """True when the header fits at every width."""
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width in WIDTHS:
            page = browser.new_page(
                viewport={"width": width, "height": 800},
                device_scale_factor=2,
                is_mobile=True,
                color_scheme="dark" if dark else "light",
            )
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(2000)  # third-party buttons (Google) render after load
            r = page.evaluate(MEASURE, selector)
            page.close()
            if r is None:
                print(f"no element matches {selector!r}")
                return False
            fits = r["right"] <= width - margin and r["scrollWidth"] <= width
            ok &= fits
            print(f"{width:>4}px  {'fits    ' if fits else 'OVERFLOW'}  rightmost={r['right']} scrollWidth={r['scrollWidth']}")
        browser.close()
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url")
    parser.add_argument("--selector", default="nav")
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--margin", type=int, default=16)
    args = parser.parse_args()
    return 0 if check(args.url, args.selector, args.dark, args.margin) else 1


if __name__ == "__main__":
    sys.exit(main())
