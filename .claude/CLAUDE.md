# lillorepo — Claude Notes

Claude-specific notes for this repository.

## Read Order

1. Read `CLAUDE.md` as the canonical repository-wide guide.
2. Read `.claude/skills/<skill>/SKILL.md` when a task maps to a skill.
3. Use `.claude/` only for Claude-specific commands, hooks, and runtime config.

## Claude-Specific Surface

- Skills: `.claude/skills/` — **generic only** (see below)
- Hooks: `.claude/hooks/`
- Runtime config: `.claude/settings.json`

## Where a skill belongs

**Generic here, domain in its package.** A skill lives at the root only if it
would still make sense in a repo that had never heard of Biwenger. Anything
that assumes a package's domain lives in that package's own `.claude/skills/`,
and Claude Code prefers it over a root skill of the same name when you are
working inside that package.

| Scope | Location | Index |
|---|---|---|
| Repo-wide | `.claude/skills/` | this file |
| `biwenger_tools` | [`packages/biwenger_tools/.claude/`](../packages/biwenger_tools/.claude/CLAUDE.md) | its own `CLAUDE.md` |

Each `.claude/` indexes only its own skills. Adding a package-scoped skill
means creating that package's `.claude/CLAUDE.md` if it has none yet — an
unindexed skill is one nobody remembers exists.

### Generic skills

| Skill | When |
|---|---|
| `add-python-dep` | Adding a PyPI dependency — keeps the five dependency layers in sync. |
| `check-deps` | Snapshot the pinned versions (Bazel, Python, modules, Actions). |
| `docs-audit` | Hunt broken links and drifted cross-references across every doc. |
| `release-notes` | Write a package's release-notes entry from recent commits. |
| `rpi-research` · `rpi-plan` · `rpi-implement` · `rpi-common` | The research → plan → implement workflow. |
| `google-cloud-*` · `google-firebase-basics` | Vendored from `google/skills` by `scripts/sync-google-skills.sh`. **Do not edit** — the sync overwrites them. |

## Key References

- `CLAUDE.md` (project root)
- `docs/setup/ai/claude-code-setup.md`
- `docs/technical/ai/claude-code-roadmap.md`

## Code comments — no testaments

Comments and docstrings must explain *what the reader needs to know to use the
code*, not the history of how it got written. Two audits already had to clean
this up: `695eb39` (drop dated/narrative code comments) and `ccb5314` (trim
over-verbose comments). Do not make it a third.

**Allowed:**
- One-line docstring stating the contract (inputs, outputs, side effects).
- A short comment when the *why* is non-obvious — a hidden constraint, a
  subtle invariant, a workaround for a specific upstream bug.
- New names that make the intent self-evident (prefer renaming over commenting).

**Forbidden:**
- Dates in comments (`# 2026-05-24`, `Until 2026-05-…`, `Empíricamente
  (2026-05-23)`, `captured 2026-05-23`, etc.). Provenance belongs in
  `git blame`, not in the source.
- Narrative about who asked for the change or when (`# by the user's call`,
  `# regression spotted 2026-05-24, fixed in this commit`, `# user asked to…`).
- Commit-scope references (`# added in this PR`, `# see commit abc123`).
- Restating what well-named code already says (`# read the cash` above
  `cash = ctx.biwenger.cash()`).
- Multi-paragraph docstrings that recap history or list every caller.

If the comment would not survive the next refactor without becoming a lie,
it does not belong in the source. Put it in the PR description.

## Working style

When the user green-lights a task, implement it end-to-end without asking for
confirmation at each step — they prefer reviewing a finished diff over
approving increments. The checkpoint is git: do not commit or push until the
user has seen the result or explicitly asked for the full branch → PR → merge
flow in the current conversation.
