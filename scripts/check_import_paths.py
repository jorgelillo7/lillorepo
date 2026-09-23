#!/usr/bin/env python3
"""Fail when code reaches other code by path instead of through Bazel.

    python3 scripts/check_import_paths.py

python-conventions LP-9: shared code is a `deps` edge, never a path. The CI
test selector (`scripts/affected_tests.py`) reasons over the Bazel graph, so an
edge the graph does not know about is a consumer CI will not re-test when its
dependency changes. Two shapes are caught:

- an `imports` entry in a BUILD file that climbs out of its package (`..`);
- deployed code mutating `sys.path` or calling `site.addsitedir`.

Scripts run by hand from the repo root, and tests, are the sanctioned
exception: they bootstrap `sys.path` so they run with nothing installed.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_MUTATION = re.compile(
    r"^[^#]*\b(?:sys\.path\s*(?:\.(?:insert|append|extend)\s*\(|\+=|=(?!=)"
    r"|\[[^\]]*\]\s*=(?!=))"
    r"|site\.addsitedir\s*\()"
)
_IMPORTS = re.compile(r"\bimports\s*=\s*\[([^\]]*)\]")


def mutates_sys_path(line: str) -> bool:
    """True when the line changes `sys.path`, rather than merely naming it."""
    return bool(_MUTATION.search(line))


def may_touch_sys_path(path: str) -> bool:
    """Scripts and tests may bootstrap `sys.path`; deployed code may not."""
    parts = Path(path).parts
    return parts[0] == "scripts" or "scripts" in parts or "tests" in parts


def escaping_imports(build_text: str) -> list[str]:
    """Every `imports` entry that climbs out of its package."""
    return [
        entry
        for block in _IMPORTS.findall(build_text)
        for entry in re.findall(r'"([^"]*)"', block)
        if ".." in Path(entry).parts
    ]


def _tracked(*patterns: str) -> list[str]:
    return subprocess.run(
        ["git", "ls-files", *patterns],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()


def main() -> int:
    errors: list[str] = []
    for path in _tracked("*BUILD.bazel"):
        for entry in escaping_imports((REPO_ROOT / path).read_text()):
            errors.append(f"{path}: imports entry {entry!r} escapes its package")
    for path in _tracked("*.py"):
        if may_touch_sys_path(path):
            continue
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if mutates_sys_path(line):
                errors.append(f"{path}:{number}: deployed code mutates sys.path")

    if errors:
        print("Code reaches other code by path (python-conventions LP-9):\n")
        for error in errors:
            print(f"  - {error}")
        print("\nDepend on the target in BUILD.bazel instead.")
        return 1
    print("==> import paths OK (no sys.path in deployed code, no escaping imports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
