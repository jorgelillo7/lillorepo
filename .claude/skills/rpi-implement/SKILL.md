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
1. Run the script at `.claude/skills/rpi-common/scripts/check-plannotator.sh` — if it fails, stop immediately and show the error to the user.
2. Run the script at `.claude/skills/rpi-common/scripts/ensure-rpi-dirs.sh`

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

A task that adds or changes behaviour in `logic/` or `core/` is written as
three lines, not one — the loop from
`docs/technical/backend/python-conventions.md` § 6, made visible in the artifact
this skill already produces:

```markdown
- [ ] Task 3: <the behaviour change>
  - [ ] red: `bazel test //path:target` run and observed failing (reason: …)
  - [ ] green: the same target passing
```

Check `red` before writing the implementation. It costs one extra run and it is
the only evidence the test can fail at all — a test written next to its own
implementation passes whether or not it asserts anything true, which is how
green tests in this repo ended up pinning defects. This does not change the
"do not stop between tasks" rule below: nothing here waits for the user.

Once the todo file is created, implement every task one by one. After completing each task, mark it as done in the todo file (`- [x]`). Do not stop between tasks — implement everything without pausing to ask the user for confirmation.

When all tasks are done, inform the user that the implementation is complete.

Only pause and notify the user if a task is truly impossible to implement without external input (e.g. missing credentials, unavailable service, unresolvable dependency). This should be extremely rare. In all other cases, keep going.
