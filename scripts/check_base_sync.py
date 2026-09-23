#!/usr/bin/env python3
"""Verify the three dependency layers still agree with each other.

Bazel resolves `requirements_lock.txt` for tests and local runs; production
runs whatever `docker/Dockerfile.base` pip-installs into the base image. The
two are kept in step by hand (see the `add-python-dep` skill), and nothing
noticed when they drifted: the failure mode is green tests plus an
`ImportError` at cold start, with no revision rollback to fall back on.

Three checks:

1. Every module `requirements.txt` reaches `requirements.in`. Catches a
   regenerated `requirements.in` that silently dropped a module.
2. Every runtime package in the lock is installed in the image.
3. Their versions match.
4. Every `@pypi//x` / `requirement("x")` a BUILD or .bzl file consumes is
   declared directly in some module `requirements.txt` (python-conventions
   LP-2). A transitive-only pin is a version someone else's resolution chose,
   and the next regeneration can move it with no diff anyone reviews.

Runtime vs dev is derived from pip-compile's own `# via` annotations, walked
down from the roots each module declares — never from a list maintained here,
which would rot exactly like the thing it guards. The dev roots are the lines
below the `DEV_MARKER` in `core/requirements.txt`.

    python3 scripts/check_base_sync.py

Exits non-zero on any mismatch.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_MARKER = "# dev-only"


def canonical(name: str) -> str:
    """PEP 503 normalisation: case-insensitive, and `-`, `_`, `.` alike."""
    return re.sub(r"[-_.]+", "-", re.sub(r"\[.*\]$", "", name.strip()).lower())


def module_requirements() -> dict[Path, tuple[set[str], set[str]]]:
    """`{path: (runtime_roots, dev_roots)}` for every module requirements.txt.

    Everything below `DEV_MARKER` is a development dependency, deliberately
    absent from the runtime image. Marking it in the file rather than here
    means whoever adds a dev dep sees the rule at the point of the change.
    """
    out = {}
    globs = [REPO_ROOT / "core", REPO_ROOT / "packages"]
    for root in globs:
        for path in sorted(root.rglob("requirements.txt")):
            runtime, dev, in_dev = set(), set(), False
            for line in path.read_text().splitlines():
                stripped = line.strip()
                if stripped.lower().startswith(DEV_MARKER):
                    in_dev = True
                    continue
                if not stripped or stripped.startswith("#"):
                    continue
                name = canonical(re.split(r"[<>=;\[]", stripped)[0])
                (dev if in_dev else runtime).add(name)
            out[path] = (runtime, dev)
    return out


_LABEL = re.compile(
    r'@pypi//([A-Za-z0-9_.-]+)|requirement\(\s*"([A-Za-z0-9_.-]+)"\s*\)'
)


def consumed_distributions(build_text: str) -> set[str]:
    """Every distribution a BUILD or .bzl file consumes, canonicalised."""
    return {canonical(a or b) for a, b in _LABEL.findall(build_text)}


def undeclared_labels(
    build_texts: dict[str, str], declared: set[str]
) -> list[tuple[str, str]]:
    """`[(file, distribution)]` consumed without a direct declaration."""
    return [
        (path, name)
        for path, text in sorted(build_texts.items())
        for name in sorted(consumed_distributions(text))
        if name not in declared
    ]


def build_files() -> dict[str, str]:
    """`{path: text}` for every tracked BUILD.bazel and .bzl file."""
    listed = subprocess.run(
        ["git", "ls-files", "*BUILD.bazel", "*.bzl"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return {path: (REPO_ROOT / path).read_text() for path in listed}


def parse_lock() -> tuple[dict[str, str], dict[str, set[str]]]:
    """`({package: version}, {package: {packages that require it}})`.

    pip-compile writes each pin followed by an indented `# via` block naming
    the parents; a direct dependency is `via -r requirements.in`.
    """
    versions: dict[str, str] = {}
    parents: dict[str, set[str]] = {}
    current = None
    for line in (REPO_ROOT / "requirements_lock.txt").read_text().splitlines():
        pin = re.match(r"^([A-Za-z0-9._-]+(?:\[[^\]]*\])?)==([^\s;]+)", line)
        if pin:
            current = canonical(pin.group(1))
            versions[current] = pin.group(2)
            parents.setdefault(current, set())
            continue
        if current and line.startswith(" "):
            via = line.strip().lstrip("#").strip()
            if via.startswith("via"):
                via = via[3:].strip()
            if via and not via.startswith("-r "):
                parents[current].add(canonical(via))
    return versions, parents


def parse_dockerfile() -> dict[str, str]:
    """`{package: version}` installed into the production base image."""
    text = (REPO_ROOT / "docker" / "Dockerfile.base").read_text()
    return {
        canonical(m.group(1)): m.group(2)
        for m in re.finditer(r"^\s+([A-Za-z0-9._-]+)==([^\s\\]+)", text, re.M)
    }


def runtime_closure(roots: set[str], parents: dict[str, set[str]]) -> set[str]:
    """Every package reachable from `roots`, following `# via` edges downward.

    A package pulled in by both a runtime and a dev root counts as runtime:
    the image needs it either way.
    """
    reachable = {p for p in parents if p in roots}
    changed = True
    while changed:
        changed = False
        for package, via in parents.items():
            if package not in reachable and via & reachable:
                reachable.add(package)
                changed = True
    return reachable


def main() -> int:
    errors: list[str] = []
    modules = module_requirements()

    # 1. Every module's requirements.txt reaches the generated requirements.in.
    requirements_in = (REPO_ROOT / "requirements.in").read_text()
    for path in modules:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel not in requirements_in:
            errors.append(
                f"{rel} is missing from requirements.in — regenerate it "
                f"(docs/operations.md, 'Regenerate the central requirements.in')"
            )

    versions, parents = parse_lock()
    docker = parse_dockerfile()

    runtime_roots: set[str] = set()
    dev_roots: set[str] = set()
    for runtime, dev in modules.values():
        runtime_roots |= runtime
        dev_roots |= dev

    needed = runtime_closure(runtime_roots, parents)

    # 2 + 3. Everything the runtime needs is in the image, at the same version.
    for package in sorted(needed):
        if package not in docker:
            errors.append(
                f"{package}=={versions[package]} is a runtime dependency but is "
                f"not installed in docker/Dockerfile.base"
            )
        elif docker[package] != versions[package]:
            errors.append(
                f"{package}: lock has {versions[package]}, "
                f"Dockerfile.base has {docker[package]}"
            )

    # 4. Every consumed label is a direct declaration (LP-2).
    declared = set().union(*(runtime | dev for runtime, dev in modules.values()))
    for path, name in undeclared_labels(build_files(), declared):
        errors.append(
            f"{path} consumes {name}, which no module requirements.txt declares "
            f"— add it where it is used (python-conventions LP-2)"
        )

    if errors:
        print("Dependency layers are out of sync:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            "\nSee the `add-python-dep` skill — it walks all five layers.",
            file=sys.stderr,
        )
        return 1

    dev_only = len({p for p in versions if p not in needed})
    print(
        f"==> dependency layers OK "
        f"({len(needed)} runtime packages pinned alike in the lock and the "
        f"base image, {dev_only} dev-only packages correctly absent)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
