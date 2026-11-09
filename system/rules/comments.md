# Code comments — no testaments

Comments and docstrings explain *what the reader needs to know to use the
code*, not how it got written. Narrative comments turn false after the next
refactor, and they have had to be swept out of a codebase before.

**Allowed:**
- One-line docstring stating the contract (inputs, outputs, side effects).
- A short comment when the *why* is non-obvious — a hidden constraint, a
  subtle invariant, a workaround for a specific upstream bug.
- A better name instead of a comment.

**Forbidden:**
- Dates (`# 2026-05-24`, `Until 2026-05-…`, `captured 2026-05-23`).
  Provenance belongs in `git blame`.
- Narrative about who asked or when (`# by the user's call`, `# regression
  spotted…, fixed in this commit`).
- Commit or PR references (`# added in this PR`, `# see commit abc123`).
- Restating what the code already says (`# read the cash` above
  `cash = ctx.biwenger.cash()`).
- Multi-paragraph docstrings that recap history or list every caller.

If a comment would not survive the next refactor without becoming a lie, it
belongs in the PR description.
