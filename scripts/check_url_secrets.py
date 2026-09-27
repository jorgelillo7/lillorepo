"""Refuse a credential written literally into a URL in a tracked file.

The Jornada Perfecta app token sat in a public doc for five months as
`...fitness-daily?auth=<value>`. GitHub secret scanning never flagged it: it
only knows the formats of providers it partners with, and a third party's
embedded token has none. This check knows the shape instead — a query
parameter named like a credential with a literal value — so the next one is
caught whatever service it belongs to.

Placeholders pass: `auth=<JP_TOKEN>`, `key=${KEY}`, `token={token}`,
`key=YOUR_KEY`, `key=...`.
"""

import re
import subprocess
import sys

URL_SECRET = re.compile(
    r"https?://[^\s'\"`)<>]*?[?&]"
    r"(auth|token|access_token|api_?key|apikey|key|secret|password)="
    r"(?![<{$%*]|\.\.\.|x{3}|your|tu_)"
    r"([^&\s'\"`)<>\]]+)",
    re.IGNORECASE,
)
BINARY = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff2", ".ttf", ".lock")


def offenders(text: str) -> list[tuple[int, str]]:
    """`(line number, parameter name)` for each literal credential in a URL."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in URL_SECRET.finditer(line):
            found.append((number, match.group(1)))
    return found


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split()
    bad = []
    for path in tracked:
        if path.endswith(BINARY):
            continue
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        bad += [(path, number, name) for number, name in offenders(text)]

    if bad:
        print("\nA credential is written literally into a URL:\n")
        for path, number, name in bad:
            print(f"  {path}:{number}  ({name}=…)")
        print(
            "\nReplace the value with a placeholder such as `<TOKEN>`; the real\n"
            "one belongs in Secret Manager. If it was ever pushed, treat it as\n"
            "public.\n"
        )
        return 1
    print(f"==> url secrets OK ({len(tracked)} tracked files, none in a URL)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
