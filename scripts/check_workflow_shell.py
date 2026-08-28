"""Refuse a comment inside a backslash-continued shell command.

This has broken production twice. A `run: |` block that reads

    gcloud run deploy foo \\
      --update-secrets="..." \\
      # why the next flag looks like that
      --set-env-vars="..."

does not do what it looks like. The shell joins the continued line with the
comment and swallows everything after it, so the command runs **without the
flags below the comment** — and the next line executes as a command of its
own, which is the exit 127 you eventually see in the log.

The dangerous part is that the truncated command often succeeds. The web
service was deployed with a new image and the previous revision's environment
for an hour before anyone noticed, because `gcloud run deploy` is perfectly
happy without `--set-env-vars`.

Comments above the command are fine. Only the continuation is a trap.
"""

import sys
from pathlib import Path

WORKFLOWS = Path(".github/workflows")


def offenders(text: str) -> list[tuple[int, str]]:
    """`(line number, the comment)` for each comment continuing a command."""
    found = []
    lines = text.splitlines()
    for index, line in enumerate(lines[:-1]):
        if not line.rstrip().endswith("\\"):
            continue
        nxt = lines[index + 1].strip()
        if nxt.startswith("#"):
            found.append((index + 2, nxt))
    return found


def main() -> int:
    if not WORKFLOWS.is_dir():
        print("no .github/workflows — nothing to check")
        return 0

    bad = []
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        for line_no, comment in offenders(path.read_text(encoding="utf-8")):
            bad.append((path, line_no, comment))

    if bad:
        print("\nA comment continues a shell command, which truncates it:\n")
        for path, line_no, comment in bad:
            print(f"  {path}:{line_no}")
            print(f"      {comment}")
        print(
            "\nThe shell joins the trailing `\\` with the comment and drops every\n"
            "flag below it. Move the comment above the command.\n"
        )
        return 1

    checked = len(list(WORKFLOWS.glob("*.yml"))) + len(list(WORKFLOWS.glob("*.yaml")))
    print(
        f"==> workflow shell OK ({checked} workflows, no comment truncates a command)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
