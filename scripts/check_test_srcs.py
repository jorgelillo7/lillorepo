#!/usr/bin/env python3
"""Fail when a `py_test` lists the code it tests among its own `srcs`.

Bazel does not instrument a test target's own files, so code listed there runs
and is tested but never reaches the coverage report: it simply disappears from
CI's coverage summary. Code under test belongs in a `py_library` the test
depends on; a test target's `srcs` hold only test files (`tests/…`,
`test_*.py`).

    python3 scripts/check_test_srcs.py

Needs Bazel (one `bazel query`); exits non-zero on any misplaced source.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_TEST_FILE = re.compile(r"[:/]tests?/|[:/]test_[^/:]*\.py$")


def misplaced(labels: list[str]) -> list[str]:
    """The Python source labels of test targets that are not test files."""
    return [
        label
        for label in labels
        if label.endswith(".py") and not _TEST_FILE.search(label)
    ]


def main() -> int:
    labels = subprocess.run(
        ["bazel", "query", "labels(srcs, kind(py_test, //...))"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if not labels:
        raise RuntimeError("bazel query returned no py_test sources")
    bad = misplaced(labels)
    if bad:
        print("\nCode under test is listed in a py_test's own srcs:\n")
        for label in bad:
            print(f"  {label}")
        print(
            "\nBazel does not instrument a test target's own files, so its "
            "coverage would\nvanish. Move them to a py_library the test "
            "depends on.\n"
        )
        return 1
    print(f"==> test srcs OK ({len(labels)} sources, only test files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
