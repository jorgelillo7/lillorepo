---
name: release-notes
description: Generates a new release notes entry for a package based on recent git commits and prepends it to the package's RELEASE-NOTES.md.
model-invocable: false
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# Goal

Generate a new release notes entry for a package in this monorepo, based on recent git commits, and prepend it to `packages/<package>/RELEASE-NOTES.md`.

# Step 1 — Identify the target package

List all directories under `packages/` that have a `RELEASE-NOTES.md` file:

```bash
find packages -name "RELEASE-NOTES.md" | sort
```

If there is only one package with release notes, use it directly without asking.
If there are multiple, use `AskUserQuestion` to ask the user which package to update.

# Step 2 — Read the existing release notes

Read `packages/<package>/RELEASE-NOTES.md` to understand:
- The version numbering scheme used (e.g. `v4.0`, `v3.2`)
- The date format used (e.g. `30 September 2025`)
- The section title style (e.g. `### **v4.0 - Title (date)**`)
- The bullet style and emoji conventions

# Step 3 — Determine the new version

Read the first release notes entry (most recent) to know the current version.
Suggest the next version by incrementing the minor number (e.g. v4.0 → v4.1).

Use `AskUserQuestion` to ask:
- Version number (show the suggested value as default)
- Short title for this release (a catchy one-liner summarising the changes)

# Step 4 — Get the relevant commits

Run git log filtered to the package path since the previous release tag or a reasonable recent window.
Use a command like:

```bash
git log --oneline --no-merges -- packages/<package>/ | head -30
```

Also run without path filter to catch cross-cutting changes (e.g. core/ changes that affect this package):

```bash
git log --oneline --no-merges | head -20
```

Read the diff summary for context if commit messages are sparse:

```bash
git diff HEAD~10 HEAD --stat -- packages/<package>/
```

# Step 5 — Generate the entry

Write a new release notes entry following the exact style of the existing ones:

- Use the same heading format: `### **vX.Y - Title (D Month YYYY)**`
- Group related commits into bullet points with appropriate emojis
- Each bullet: `* **emoji Category**: Description of what changed and why it matters`
- Focus on **what changed for the user/operator**, not on implementation details
- Keep it readable and slightly opinionated in tone (match the existing voice)
- Today's date is available from the system; format it as the file uses (e.g. `25 April 2026`)

# Step 6 — Update the file

Prepend the new entry at the top of `packages/<package>/RELEASE-NOTES.md`, after the `# Project Release Notes` header and before the first existing entry.

Leave one blank line between the header and the new entry, and one blank line between the new entry and the previous first entry.

# Step 7 — Confirm

Show the user the generated entry and ask them to confirm before writing. If they want changes, adjust and confirm again.

# Rules

- Never modify existing entries — only prepend new ones.
- Always use today's actual date, not a placeholder.
- If commit history is thin or uninformative, ask the user to describe what changed before generating.
- The tone should match the existing file: enthusiastic but informative, with emojis.
- Do not add a `Co-Authored-By` line anywhere.
