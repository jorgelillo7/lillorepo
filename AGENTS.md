# AGENTS.md

Entry point for AI coding agents (Codex, Cursor, etc.) working in this repo.

Read these in order:

1. **`README.md`** — what the repo is, architecture diagram, packages table.
2. **`CLAUDE.md`** — project charter: conventions, dependency rules, branch/PR workflow, pending follow-ups pointer.
3. **`STATUS.md`** — current maturity report, capability inventory, accepted gaps.
4. **`PENDING.md`** — open follow-ups grouped by package.
5. **`packages/<pkg>/README.md`** — per-package entry point, gotchas, local dev notes.

Operational reference: **`docs/operations.md`** (repo-wide workflows) plus a
per-package **`packages/*/OPERATIONS.md`** for that package's build/test/deploy
commands.

Skills + hooks for Claude Code live under `.claude/`.

---

## Subagent roles (`.claude/agents/`)

Four roles, each a file with its own model and tool set. The orchestrating
session stays whoever you are talking to; none of these can be that.

| Role | Model | Use it for | Returns |
|---|---|---|---|
| `dev` | sonnet | A change already decided — migrating call sites, repetitive tests, propagating a pattern | The diff, plus the commands it ran |
| `qa` | sonnet | Running suites, reproducing a bug, sweeping edge cases | Evidence: commands and their real output |
| `reviewer` | opus | Cold-eyed review of a branch, against this repo's traps | Findings with the input that breaks them |
| `spec` | opus | Writing or checking `openspec/` | Spec deltas and `check_specs.py` output |

### What this buys, and what it does not

Three things are real:

- **Model split.** Mechanical work does not need the expensive model, and
  saying so per-role is cheaper than deciding per-task.
- **Context isolation.** A test sweep or a log trawl produces thousands of
  lines. Run in a subagent, the orchestrating session receives the conclusion
  and the evidence, not the noise. In a long session this is the scarce
  resource.
- **Cold eyes.** The author cannot question an assumption they still hold. The
  three defects of 2026-08-08/09 were all tests asserting a bug as correct
  behaviour, written by whoever wrote the bug.

Three things are not:

- **They do not talk to each other.** The session spawns one, it works alone,
  it reports back. Any coordination happens in the orchestrator.
- **They start cold.** Whatever they need to know goes in the prompt, or they
  re-derive it from the repo — slowly, and sometimes wrongly.
- **They do not remove verification.** An agent reporting "all green" is worth
  what its pasted output is worth. This is why every role returns evidence
  rather than a verdict.

### When not to reach for one

If writing the brief costs more than doing the work, do the work. A subagent
earns its keep on tasks that are long, noisy, or better judged by someone who
did not write the code — not on small ones.

`/code-review ultra` already runs a multi-agent review of the current branch in
the cloud, and is billed separately. `reviewer` is the local, cheaper, more
repo-specific version of the same instinct; they are not substitutes for each
other.
