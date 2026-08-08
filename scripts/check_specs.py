#!/usr/bin/env python3
"""Verify the behaviour specs still describe code that exists.

    python3 scripts/check_specs.py

`openspec/` states what the system must do; the tests prove it holds. The two
are wired together by name — each scenario names the test that verifies it —
and nothing checked that wiring. A spec naming a renamed test is not a stale
comment, it is misinformation: it claims coverage that is not there, and the
next reader trusts it.

Two checks with different severities, because they are different kinds of
problem:

- **Broken test references fail.** A named test either exists or it does not;
  there is no judgement involved. One was found on 2026-08-08 —
  `test_gate_on_calls_biwenger_transfer_and_resolves_offer_id`, renamed a
  while back — after the check had been written ad hoc twice in one session.
- **Scenarios with no verifier warn.** The repo's own rule calls that a gap,
  but whether a given scenario is worth a test is a judgement, and a gate that
  forces one invites a test written to satisfy the gate.

A reference resolves against either a test function or a test file: specs
legitimately point at both, and an early version of this check that only knew
about functions reported 27 false positives.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS = REPO_ROOT / "openspec" / "specs"


def known_tests() -> set[str]:
    """Every test function and every test file, by name."""
    functions = subprocess.run(
        ["git", "grep", "-ho", "-E", r"def (test_[A-Za-z0-9_]+)"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout
    files = subprocess.run(
        ["git", "ls-files", "*test_*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout
    return set(re.findall(r"def (test_[A-Za-z0-9_]+)", functions)) | {
        Path(p).stem for p in files.split()
    }


def scenarios(text: str) -> list[tuple[str, bool]]:
    """`[(title, has_verifier)]` for one spec, in document order."""
    blocks = re.split(r"^#+\s*Scenario:\s*", text, flags=re.M)[1:]
    return [(b.splitlines()[0].strip(), "*Verifies:*" in b) for b in blocks]


def main() -> int:
    if not SPECS.is_dir():
        print(f"No specs directory at {SPECS}", file=sys.stderr)
        return 1

    tests = known_tests()
    specs = sorted(SPECS.rglob("spec.md"))
    broken: list[str] = []
    unverified: list[str] = []
    total_scenarios = 0

    for spec in specs:
        rel = spec.relative_to(SPECS).as_posix()
        text = spec.read_text()
        for name in sorted(set(re.findall(r"\b(test_[A-Za-z0-9_]+)", text))):
            if name not in tests:
                broken.append(f"{rel} → {name}")
        for title, verified in scenarios(text):
            total_scenarios += 1
            if not verified:
                unverified.append(f"{rel} → {title}")

    # A capability directory with no spec is a capability nobody described.
    missing = [
        d.relative_to(SPECS).as_posix()
        for d in sorted(SPECS.glob("*/*"))
        if d.is_dir() and not (d / "spec.md").exists()
    ]

    if unverified:
        print(f"==> {len(unverified)} scenario(s) with no test named:")
        for line in unverified:
            print(f"      {line}")
    if missing:
        print(f"==> {len(missing)} capability directory(ies) with no spec.md:")
        for line in missing:
            print(f"      {line}")

    if broken or missing:
        if broken:
            print("\nSpecs name tests that do not exist:\n", file=sys.stderr)
            for line in broken:
                print(f"  - {line}", file=sys.stderr)
            print(
                "\nA spec claiming coverage that is not there is worse than "
                "no spec.\nRename the reference, or point it at what replaced "
                "the test.",
                file=sys.stderr,
            )
        return 1

    print(
        f"==> specs OK ({len(specs)} specs, {total_scenarios} scenarios, "
        f"every test reference resolves)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
