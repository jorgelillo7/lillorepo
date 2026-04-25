# Global Hook Scripts

These scripts live in the repository as Claude-specific source files and can be installed into `~/.claude/`.

## Contents

| File | Type | Description |
|------|------|-------------|
| `statusline.sh` | Status line | Displays model, context usage, and total USD cost in Claude Code |
| `git-destructive-guard.py` | `PreToolUse` hook | Blocks destructive Git commands such as `push --force` and `reset --hard` |

## Example Installation For Claude Code

```bash
cp .claude/hooks/global/statusline.sh ~/.claude/statusline.sh
cp .claude/hooks/global/git-destructive-guard.py ~/.claude/hooks/git-destructive-guard.py

chmod +x ~/.claude/statusline.sh
chmod +x ~/.claude/hooks/git-destructive-guard.py
```

Add the hook to `~/.claude/settings.json`:

```json
{
  "autoUpdatesChannel": "latest",
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.sh",
    "padding": 0
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/git-destructive-guard.py"
          }
        ]
      }
    ]
  }
}
```

## Notes

- `.claude/hooks/` is the source of truth for Claude-specific hooks in this repository.
- Project-specific hooks such as `kubectl-guard.py` and `oracle-audit-log.py` also live under `.claude/hooks/`.
