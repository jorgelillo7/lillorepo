---
name: docs-audit
description: Audit every README and doc for broken links, drifted cross-references (maturity score, counts, service names) and outdated architecture descriptions. Reports findings ranked by severity; fixes the mechanical ones in a PR only when asked.
model-invocable: false
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Edit
  - Write
---

# Goal

Keep the repo's documentation honest: no broken links, no facts that have
drifted from their source of truth (maturity score, package counts, service
names, URLs), and architecture descriptions that still match the code. This
skill is **report-first** — it fixes files only when the user explicitly asks.

# Step 1 — Run the mechanical checker

```bash
bash .claude/skills/docs-audit/scripts/check_docs.sh
```

It reads the docs in scope (all `README.md`, everything under `docs/`, each
package's `OPERATIONS.md` / `DESIGN.md` / `release-notes.md`, and the root
`AGENTS.md` / `CLAUDE.md` / `STATUS.md` / `INFRA.md` / `PENDING.md`; it skips
vendored trees and the externally-synced `google-*` skills). It prints three
sections:

1. **Inventory** — what's in scope.
2. **Broken relative links** — links that don't resolve. These are **hard
   defects**, not candidates.
3. **Facts to verify** — hardcoded scores, stale-marker phrases, and packages
   missing from the root README. These are **candidates the skill must judge**,
   not automatic errors.

Show the section-2 result to the user as part 1 of the answer.

# Step 2 — Triage the broken links

Every section-2 line is a real broken link. For each, decide the fix:

- **Wrong path** (right file, wrong relative depth) → retarget the link.
- **Renamed/moved target** → point at the new path.
- **Deleted target** → remove the link or repoint to what replaced it.

Never "fix" a broken link by creating a stub file just to satisfy it.

# Step 3 — Cross-check the "facts to verify"

- **Maturity score** — `STATUS.md` is the single source of truth. Any *other*
  file that states a `X.Y / 10` score must either match it or, better, be
  changed to reference `STATUS.md` instead of duplicating the number (that's
  how the root README was fixed — a duplicated score is drift waiting to
  happen).
- **Packages missing from the root README** — decide per package: a shipped,
  deployed product belongs in the README's Packages table and architecture
  diagram; a plan-only or intentionally-unlisted package (e.g. `my_photos`) is
  fine to omit — note it as intentional, don't "fix" it.
- **Stale-marker phrases** — check whether the feature actually shipped
  (`release-notes.md`, the code). A match inside a *historical* record
  (release notes describing something already deleted) is not a defect.

# Step 4 — Judgment pass (architecture currency)

Read the architecture-bearing docs and compare against the real tree:

- **Root `README.md`** — does the mermaid diagram + Packages table include
  every deployed product under `/packages`? Are service names and URLs current?
- **`.github/workflows/README.md`** — does the deploy fan-out list match the
  jobs in `deploy.yml`?
- **Per-package `README.md`** — does each point to its own `OPERATIONS.md`?
  Do service/resource names agree with `INFRA.md`?
- **Vocabulary** — top-level dirs under `/packages` are *packages*; their
  subdirectories are *modules*. Flag drift.

Flag shipped features still described as planned, renamed services, and
descriptions that no longer match the code.

# Step 5 — Report

Structure the response:

1. **Script output** — inventory + broken links verbatim.
2. **Must-fix** — broken links and wrong facts (drifted score, missing shipped
   package, renamed service).
3. **Should-fix** — stale wording, architecture that has fallen behind.
4. **Intentional / no action** — things the checker flags that are correct by
   design (intentional Spanish, plan-only packages, historical release notes).

Rank most-severe first.

# Step 6 — Fix (ONLY if the user asks)

If the user asks to fix:

- Apply the **mechanical and clear-cut** changes: retarget broken links,
  correct a drifted number, or replace a duplicated fact with a link to its
  source of truth.
- **Do not** rewrite prose or architecture sections wholesale — *propose* those
  and let the user decide. The repo is opinionated about single-source-of-truth
  docs; the skill regularises, it does not editorialise.
- Work on a branch and open a docs-only PR (never commit to `master`), per the
  repo's branch-and-PR workflow.

# Rules

- The script is the source of truth for *current* links and inventory — don't
  re-derive them by hand.
- **Report-only by default.** Fix only on an explicit request in the same
  conversation.
- Respect intentional Spanish (the `my_photos` plan, `be_water` UI strings,
  Spanish place names, Telegram messages) — it is not a finding.
- Prefer a link over duplicated content when closing a missing cross-reference.
- Don't touch the externally-synced `google-*` skills; they track upstream via
  `scripts/sync-google-skills.sh`.
