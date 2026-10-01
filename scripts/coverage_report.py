#!/usr/bin/env python3
"""Summarise a Bazel lcov coverage report as Markdown, for CI's job summary.

    python3 scripts/coverage_report.py <lcov file> [suite ...]

Prints total and per-area line coverage, and — always — the source files no
test imports. Those are absent from an lcov report rather than at 0 %, so a
percentage alone overstates what is tested. Report-only: it never fails on a
low number, only on a missing or empty report (the coverage step broke).
"""

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_NOT_SOURCE = re.compile(
    r"(^|/)tests?/|(^|/)test_[^/]*\.py$|__init__\.py$|^\.claude/skills/google-"
)


@dataclass
class Summary:
    lines: int
    hit: int
    areas: dict = field(default_factory=dict)
    invisible: list = field(default_factory=list)


def parse_lcov(text: str) -> dict[str, tuple[int, int]]:
    """`{path: (lines, hit)}`; a file two suites report keeps its best count."""
    cov: dict[str, tuple[int, int]] = {}
    path, found, hit = None, 0, 0
    for line in text.splitlines():
        if line.startswith("SF:"):
            path, found, hit = line[3:].strip(), 0, 0
        elif line.startswith("LF:"):
            found = int(line[3:])
        elif line.startswith("LH:"):
            hit = int(line[3:])
        elif line == "end_of_record" and path:
            best = cov.get(path, (0, 0))
            cov[path] = (max(best[0], found), max(best[1], hit))
            path = None
    if not cov:
        raise ValueError("no coverage records — the coverage step produced nothing")
    return cov


def source_files(files: list[str]) -> list[str]:
    """The tracked Python files that are code under test, not tests."""
    return sorted(
        f for f in files if f.endswith(".py") and not _NOT_SOURCE.search(f)
    )


def area_of(path: str) -> str:
    """`packages/<pkg>/<module>` for package code, `packages/<pkg>` for a file at
    a package's root, the top directory otherwise."""
    parts = path.split("/")
    if parts[0] == "packages":
        return "/".join(parts[:3] if len(parts) > 3 else parts[:2])
    return parts[0]


def summarise(cov: dict[str, tuple[int, int]], sources: list[str]) -> Summary:
    areas: dict[str, tuple[int, int]] = {}
    for path, (found, hit) in cov.items():
        a = area_of(path)
        prev = areas.get(a, (0, 0))
        areas[a] = (prev[0] + found, prev[1] + hit)
    return Summary(
        lines=sum(f for f, _ in cov.values()),
        hit=sum(h for _, h in cov.values()),
        areas=dict(sorted(areas.items())),
        invisible=[s for s in sources if s not in cov],
    )


def _pct(hit: int, lines: int) -> str:
    return f"{100 * hit / lines:.1f} %" if lines else "—"


def render(summary: Summary, suites: list[str]) -> str:
    out = [
        "## Coverage",
        "",
        f"**{_pct(summary.hit, summary.lines)}** of the lines in files a test "
        f"imports ({summary.hit:,} / {summary.lines:,}). Report-only.",
        "",
        "| Area | Lines | Covered |",
        "|---|---:|---:|",
    ]
    for area, (found, hit) in summary.areas.items():
        out.append(f"| `{area}` | {found:,} | {_pct(hit, found)} |")
    out += [
        "",
        f"**{len(summary.invisible)} source files no test imports** — absent "
        "from the report, so not in the percentage.",
        "",
        "<details><summary>Which files</summary>",
        "",
    ]
    out += [f"- `{path}`" for path in summary.invisible] or ["- none"]
    out += ["", "</details>"]
    if suites:
        out += ["", "Suites measured:", ""] + [f"- `{s}`" for s in suites]
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    report = Path(argv[0])
    if not report.is_file():
        raise FileNotFoundError(f"no coverage report at {report}")
    cov = parse_lcov(report.read_text(encoding="utf-8"))
    tracked = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    print(render(summarise(cov, source_files(tracked)), suites=argv[1:]), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
