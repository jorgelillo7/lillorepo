# lillorepo — Claude Notes

Claude-specific notes for this repository.

## Read Order

1. Read `CLAUDE.md` as the canonical repository-wide guide.
2. Read `.claude/skills/<skill>/SKILL.md` when a task maps to a skill.
   Read `.claude/agents/<role>.md` before delegating to that role — it says
   what the role is for and, more usefully, what it must not do.
3. Use `.claude/` only for Claude-specific commands, hooks, and runtime config.

## Claude-Specific Surface

- Skills: `.claude/skills/` — **generic only** (see below)
- Agents: `.claude/agents/` — the four subagent roles, documented in
  [`../AGENTS.md`](../AGENTS.md)
- Rules: `.claude/rules/` — `python.md`, loaded only when a Python, `BUILD.bazel` or requirements file is opened
- Hooks: `.claude/hooks/`
- Runtime config: `.claude/settings.local.json` — per machine and gitignored; the repo ships no shared `settings.json`

## Where a skill belongs

**Generic here, domain in its package.** A skill lives at the root only if it
would still make sense in a repo that had never heard of Biwenger. Anything
that assumes a package's domain lives in that package's own `.claude/skills/`,
and Claude Code prefers it over a root skill of the same name when you are
working inside that package.

| Scope | Location | Index |
|---|---|---|
| The machine, any project | [`system/skills/`](../system/skills/), installed into `~/.claude/skills/` by `scripts/install-system.sh` | the table below |
| Repo-wide | `.claude/skills/` | this file |
| `biwenger_tools` | [`packages/biwenger_tools/.claude/`](../packages/biwenger_tools/.claude/CLAUDE.md) | its own `CLAUDE.md` |
| `interactive_fiction` | [`packages/interactive_fiction/.claude/`](../packages/interactive_fiction/.claude/CLAUDE.md) | its own `CLAUDE.md` |

Each `.claude/` indexes only its own skills. Adding a package-scoped skill
means creating that package's `.claude/CLAUDE.md` if it has none yet — an
unindexed skill is one nobody remembers exists.

### Generic skills

| Skill | When |
|---|---|
| `add-python-dep` | Adding a PyPI dependency — keeps the five dependency layers in sync. |
| `check-deps` | Snapshot the pinned versions (Bazel, Python, modules, Actions). |
| `docs-audit` | Hunt broken links and drifted cross-references across every doc. |
| `openspec-backfill` | Write the `openspec/` spec for code that already ships without one. |
| `openspec-propose` | Agree the behaviour of a feature that does not exist yet, before writing it. |
| `release-notes` | Write a package's release-notes entry from recent commits. |
| `security-sweep` | Sweep one or more repos for leaked secrets, key files, advisories and risky GitHub or workflow settings. |
| `ship` | Merge a PR and prove it reached production — head check, no stacking, deploy watch, revisions serving. |
| `google-cloud-*` · `google-firebase-basics` | Vendored from `google/skills` by `scripts/sync-google-skills.sh`. **Do not edit** — the sync overwrites them. |

### Personal skills and rules (`system/`)

Kept here so they are versioned with everything else, but about the Mac and
the owner's habits, not this repo: `scripts/install-system.sh` copies
`system/skills/` into `~/.claude/skills/` and `system/rules/` into
`~/.claude/rules/`, so they load in every project. Edit them here and run it
again; the installed copies are overwritten.

Rules (`system/rules/`), loaded at the start of every session: `language`,
`verify`, `lists`, `comments`, `git`, `working-style`, `machine`.

Skills (`system/skills/`):

| Skill | When |
|---|---|
| `audit-mac-tools` | Audit the machine's toolchain — what is stale, what is abandoned, what only looks stale. |
| `audit-apple-contacts` | Audit the Apple address book and merge a Google export into it — one-by-one approval, nothing written until the owner says so. |
| `mac-cleanup` | Measure the disk and recover space — nothing deleted without the owner's yes in that round. |

## Agents vs skills

A **skill** is a procedure: the same steps every time, for a task you do
rarely enough to forget. An **agent** is a worker with a role, its own model
and its own context — you delegate to it and read what it returns.

Reach for an agent when the work is long, noisy, or better judged by someone
who did not write the code. Not when writing the brief costs more than doing
the job.

Agents are repo-wide and not package-scoped, unlike skills: a reviewer that
only knew one package would miss the interactions that produce most defects
here.

## Key References

- `CLAUDE.md` (project root)
- `docs/setup/ai/claude-code-setup.md`
- `docs/technical/ai/claude-code-roadmap.md`
