#!/usr/bin/env python3
"""
PreToolUse hook — blocks destructive Git commands before execution.
Only acts when a real subcommand invokes `git` with a dangerous operation.
Global hook — see `.claude/hooks/global/README.md` for installation.
"""
import json
import sys
import re

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")

DANGEROUS_OPS = [
    "push --force",
    "push -f",
    "reset --hard",
    "clean -f",
    "clean -fd",
    "checkout -- ",
    "restore .",
    "branch -D",
]

# Split the command into real subcommands (&&, ||, ;, |, \n)
subcommands = re.split(r'&&|\|\||;|\n|\|', cmd)

matched_op = None
matched_subcmd = None

for subcmd in subcommands:
    tokens = subcmd.strip().split()
    if not tokens:
        continue
    # Look for 'git' as a real token, not inside strings or wrapper commands.
    try:
        git_idx = next(i for i, t in enumerate(tokens) if t == "git" or t.endswith("/git"))
    except StopIteration:
        continue
    # Reconstruct the Git portion of the subcommand.
    git_part = " ".join(tokens[git_idx:])
    for op in DANGEROUS_OPS:
        if op in git_part:
            matched_op = op
            matched_subcmd = git_part
            break
    if matched_op:
        break

if not matched_op:
    print(json.dumps({"decision": "approve"}))
    sys.exit(0)

print(json.dumps({
    "decision": "block",
        "reason": (
        f"⚠️  GIT GUARD: Destructive operation intercepted.\n"
        f"  Detected pattern: {matched_op!r}\n"
        f"  Subcommand: {matched_subcmd}\n\n"
        f"  This command can cause unrecoverable work loss.\n"
        f"  If you really want to proceed, run it directly in the terminal."
    )
}))
