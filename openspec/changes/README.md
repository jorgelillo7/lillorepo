# changes/

In-flight change proposals. One folder per change, each with:

```
{change-name}/
├── proposal.md   # why, what's changing, at a glance
├── design.md     # technical approach / trade-offs
├── tasks.md      # implementation checklist
└── specs/        # spec deltas: ADDED / MODIFIED / REMOVED requirements
```

A change captures the plan *before* the code, then updates `../specs/` when it
lands. Between changes this folder is empty (only this README). Completed
changes move to `../archive/{date}-{name}/` if you want the history; otherwise
the spec delta is folded into `../specs/` and the change folder deleted.

This mirrors the [OpenSpec](https://github.com/Fission-AI/OpenSpec) convention,
adopted as filesystem structure only — see `../project.md`.
