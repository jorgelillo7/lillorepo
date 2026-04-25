---
name: rpi-implement
description: Implementation mode skill that executes all tasks defined in an rpi plan file.
model-invocable: false
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# Goal
From now on you are in implementation mode. The final objective is to implement all the tasks defined in a plan.

# Bootstrap

Before doing anything else, run these two scripts in this exact order:
1. Run the script at `.claude/skills/rpi-common/check-plannotator.sh` — if it fails, stop immediately and show the error to the user.
2. Run the script at `.claude/skills/rpi-common/ensure-rpi-dirs.sh`

# Information from the user
The first thing you should do is use `AskUserQuestion` to ask the user which plan to implement. List the most recent files in `~/.claude/rpi/plans/` as candidates. A plan is mandatory — do not proceed without one.

- Derive the todo filename directly from the plan filename (e.g. `foo-plan.md` → `foo-todo.md`). Do not ask the user anything else.

# Rules

Read the selected plan file before doing anything else.

Create a todo file at `~/.claude/rpi/todos/<name>-todo.md`. The todo file must contain a flat markdown checklist of all granular tasks extracted from the plan, for example:

```markdown
# foo — Implementation Tasks

- [ ] Task 1
- [ ] Task 2
- [ ] Task 3
```

Once the todo file is created, implement every task one by one. After completing each task, mark it as done in the todo file (`- [x]`). Do not stop between tasks — implement everything without pausing to ask the user for confirmation.

When all tasks are done, inform the user that the implementation is complete.

Only pause and notify the user if a task is truly impossible to implement without external input (e.g. missing credentials, unavailable service, unresolvable dependency). This should be extremely rare. In all other cases, keep going.
