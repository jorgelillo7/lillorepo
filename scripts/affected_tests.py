#!/usr/bin/env python3
"""Which test targets a change can possibly break, asked of the build graph.

    python3 scripts/affected_tests.py origin/master [HEAD]

Prints one Bazel target per line, or nothing when a change cannot affect any
test. CI runs exactly those.

The mapping is **derived, never declared**. An earlier version of this idea
kept a hand-written list of targets per module in each workflow; the two
copies drifted until `draft_skill_tests` ran on pull requests and never on
master, which is the branch that deploys (fixed in #290 by running `//...`
everywhere). A list of "what belongs to what" rots because nothing checks it.
`rdeps` cannot rot: it asks the same graph Bazel builds from.

Two things `rdeps` genuinely cannot see, both of which fall back to everything:

- **Build files.** `.bzl`, `BUILD.bazel`, `MODULE.bazel` and the lock are not
  targets, so a change to the macro every service loads would come back as
  "affects nothing". That is the shape of a change that alters every image.
- **CI itself.** Editing the workflow or this script must re-run the suite it
  decides, or the decision goes unverified.

Files that are in no package at all — docs, README, PENDING.md — contribute
nothing, which is the point: a documentation change runs no tests.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# A change to any of these invalidates the graph itself, so the answer is
# "everything". Matched on the file name or the suffix.
GLOBAL_NAMES = {
    "MODULE.bazel",
    "MODULE.bazel.lock",
    "BUILD.bazel",
    "WORKSPACE",
    ".bazelrc",
    ".bazelversion",
    "requirements.in",
    "requirements_lock.txt",
    "requirements.txt",
}
GLOBAL_SUFFIXES = {".bzl"}
GLOBAL_PREFIXES = (".github/workflows/", "scripts/affected_tests.py", "platforms/")

EVERYTHING = "//..."


def changed_files(base: str, head: str = "HEAD") -> list[str]:
    diff = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in diff.stdout.splitlines() if line.strip()]


def forces_everything(path: str) -> bool:
    name = Path(path).name
    return (
        name in GLOBAL_NAMES
        or Path(path).suffix in GLOBAL_SUFFIXES
        or path.startswith(GLOBAL_PREFIXES)
    )


def label_for(path: str) -> str | None:
    """`//package:file` for a source file, or None when it is in no package.

    The package is the nearest ancestor directory holding a BUILD.bazel — the
    same rule Bazel uses.

    The **root** package does not count. Its BUILD.bazel exports exactly one
    file, `requirements_lock.txt`, which already forces everything before this
    runs; so anything else that lands there — docs, PENDING.md, STATUS.md — is
    not a target, and pretending otherwise would hand Bazel a label it does not
    know. Returning None says the honest thing: this file breaks no test.
    """
    full = REPO_ROOT / path
    for parent in [full.parent, *full.parent.parents]:
        if parent == REPO_ROOT:
            break
        if (parent / "BUILD.bazel").exists():
            package = parent.relative_to(REPO_ROOT).as_posix()
            rel = full.relative_to(parent).as_posix()
            return f"//{package}:{rel}"
    return None


def query_tests(labels: list[str]) -> list[str]:
    expr = "kind('py_test', rdeps(//..., set({})))".format(" ".join(labels))
    result = subprocess.run(
        ["bazel", "query", expr, "--output=label", "--keep_going"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    # `--keep_going` still exits non-zero when some label is unknown to the
    # graph (a file Bazel never sees). The targets it did resolve are valid.
    return sorted({t for t in result.stdout.splitlines() if t.startswith("//")})


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/master"
    head = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
    files = changed_files(base, head)
    if not files:
        return 0

    forcing = [f for f in files if forces_everything(f)]
    if forcing:
        print(f"# build graph touched: {forcing[0]}", file=sys.stderr)
        print(EVERYTHING)
        return 0

    labels = [lb for lb in (label_for(f) for f in files) if lb]
    if not labels:
        print("# no changed file belongs to a Bazel package", file=sys.stderr)
        return 0

    for target in query_tests(labels):
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
