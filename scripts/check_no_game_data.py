"""Keep `packages/emulation_thor6` free of game data.

That package's README states, to anyone who arrives at this public repository,
that it holds no ROMs, disc images, BIOS dumps or keys — and invites the reader
to verify it with `git ls-files`. This runs that check in CI so the statement
cannot quietly stop being true.

Two failure modes it exists for. Someone drops a dump in `BIOS/` or `ROMs/` and
force-adds it past the ignore rules; or an ignore rule is written on a branch
and is not in effect on the one the commit is made from, which is how a private
file reached master on 2026-08-25.

Stdlib only and offline, like the other guards `lint.sh` runs.
"""

import subprocess
import sys

PACKAGE = "packages/emulation_thor6"

# What the package legitimately contains: prose, the two scripts, and the
# empty markers that give a directory a shape. Anything else tracked under it
# is either game data or something that needs a deliberate decision.
ALLOWED_SUFFIXES = {".md", ".py", ".sh", ".bazel"}
ALLOWED_NAMES = {".gitkeep"}


def tracked_files(package: str) -> list:
    """Everything git tracks under the package. The index, not the disk —
    an ignored file on disk is fine; a tracked one is the problem."""
    result = subprocess.run(
        ["git", "ls-files", "--", package],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def offenders(paths: list) -> list:
    out = []
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        if name in ALLOWED_NAMES:
            continue
        suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if suffix.lower() not in ALLOWED_SUFFIXES:
            out.append(path)
    return out


def main() -> int:
    try:
        paths = tracked_files(PACKAGE)
    except subprocess.CalledProcessError:
        # Not a git checkout, or the package is absent. Nothing to assert.
        return 0

    bad = offenders(paths)
    if not bad:
        print(
            f"==> emulation package clean ({len(paths)} tracked files, "
            "all documentation or scripts)"
        )
        return 0

    print()
    print(f"Files tracked under {PACKAGE} that should not be:")
    print()
    for path in bad:
        print(f"  - {path}")
    print()
    print("That package's README tells anyone reading this public repository")
    print("that it holds no ROMs, disc images, BIOS dumps or keys, and invites")
    print("them to check with `git ls-files`. One of these would make that")
    print("false.")
    print()
    print("Untrack it:  git rm --cached <path>")
    print(f"Allowed:     {', '.join(sorted(ALLOWED_SUFFIXES))}, .gitkeep")
    return 1


if __name__ == "__main__":
    sys.exit(main())
