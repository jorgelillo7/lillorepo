#!/usr/bin/env python3
"""Every public page of the live sites, in light and dark: what the browser complains about.

    python3 scripts/web_console_sweep.py [--site biwenger|be_water|wishlist|draft3d ...]

Prints, per page and colour scheme, console errors and warnings, uncaught page
errors, failed requests and HTTP responses of 400 or more. Exits 1 when any page
has a console error or an uncaught error, 0 otherwise; warnings and third-party
noise (a Google iframe, WebGL performance notes) are printed but do not fail.

Needs Playwright, outside the lock on purpose (a local check, never in an image):
    pip3 install playwright && python3 -m playwright install chromium
"""

import argparse
import sys

from playwright.sync_api import sync_playwright

SITES = {
    "biwenger": (
        "https://biwenger-summary-pjpqofuevq-no.a.run.app",
        ["/26-27/", "/26-27/salseo", "/26-27/mercado", "/26-27/participacion",
         "/26-27/competiciones", "/palmares", "/reglamento", "/calendario"],
    ),
    "be_water": (
        "https://be-water-lzqhg7kcoa-no.a.run.app",
        ["/", "/agua/22", "/comunidad", "/acerca", "/recomendar", "/perfil"],
    ),
    "wishlist": ("https://wishlist.jorgelillo.workers.dev", ["/", "/?buscar=lego"]),
    "draft3d": ("https://interactive-fiction-draft3d.jorgelillo.workers.dev", ["/"]),
}


def sweep(sites: list[str]) -> bool:
    """Visit every page of `sites` in both schemes; True when none had an error."""
    clean = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for scheme in ("light", "dark"):
            context = browser.new_context(
                viewport={"width": 390, "height": 844}, color_scheme=scheme, is_mobile=True
            )
            for site in sites:
                base, paths = SITES[site]
                for path in paths:
                    clean &= _visit(context, f"{base}{path}", scheme)
            context.close()
        browser.close()
    return clean


def _visit(context, url: str, scheme: str) -> bool:
    problems: list[str] = []
    errors: list[str] = []
    page = context.new_page()
    page.on("console", lambda m: m.type in ("error", "warning") and problems.append(f"{m.type}: {m.text[:160]}"))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: (problems.append(f"pageerror: {str(e)[:160]}"), errors.append(str(e))))
    page.on("requestfailed", lambda r: problems.append(f"failed: {r.url[:110]} {r.failure}"))
    page.on("response", lambda r: r.status >= 400 and problems.append(f"HTTP {r.status}: {r.url[:110]}"))
    try:
        page.goto(url, wait_until="networkidle", timeout=45000)
    except Exception as e:  # a 3D room can keep the network busy past the timeout
        problems.append(f"goto: {str(e)[:100]}")
    page.wait_for_timeout(1500)
    page.close()
    print(f"[{scheme}] {url}: {'OK' if not problems else ''}")
    for line in sorted(set(problems)):
        print("    ", line)
    return not errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", action="append", choices=sorted(SITES), help="repeatable; default: all")
    args = parser.parse_args()
    return 0 if sweep(args.site or sorted(SITES)) else 1


if __name__ == "__main__":
    sys.exit(main())
