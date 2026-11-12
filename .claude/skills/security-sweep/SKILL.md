---
name: security-sweep
description: Sweep one or more of the owner's repositories for leaked secrets (tree and full history), key files on disk, dependency advisories, GitHub settings and risky workflow patterns, then triage the result. Use before a release, after a dependency wave, after a repo changes visibility, or when asked for a security review of a repo as a whole.
model-invocable: false
allowed-tools:
  - Bash
  - Read
---

# Goal

Turn `scripts/security_sweep.py`'s output into a short list of things the owner
must act on, and keep it from ever leaking what it found.

# When

- Before a release of any app or service.
- After a wave of dependency bumps, or when Dependabot has been quiet a while.
- When a repository becomes public, or a new one is created.
- Not in CI: it calls OSV, npm and the GitHub API.

# Step 1 — Run it

From lillorepo's root, one or more repositories at a time:

```bash
rtk proxy python3 scripts/security_sweep.py ../lillo-android-apps \
  > "$SCRATCH/sweep.txt"; echo "exit=$?"
```

- **`rtk proxy`**: the token proxy truncates long lines, which breaks `--json`
  and can cut a finding in half.
- **Write the output outside the repository.** The scratchpad is the place.
  Findings name real files and commits, and lillorepo is public.
- **personal-finance** holds bank data. Always pass
  `--exclude inbox --exclude planned.toml --exclude report.html
  --exclude deploy/public`, so those files and their diffs are never read.
- `--offline` runs only the git steps, when the network or `gh` is not at hand.

# Step 2 — Read it

Each line is `severity step rule: where  what`. Secrets show four characters
and a `[fingerprint]`, never the value. The trailing `·` lines say what each
step did or why it skipped; a skipped step is not a clean step.

| Severity | Meaning | Fails the run |
|---|---|---|
| `secret` | A credential shape, or a key/keystore/env file name, in the tree or any commit | yes |
| `critical` | An advisory OSV, npm or Dependabot rates CRITICAL | yes |
| `high` / `medium` / `low` | Rated advisories; settings and workflow risks | no |
| `unrated` | An OSV advisory with no database rating — read it, do not assume it is minor | no |
| `info` | Key files on disk that git ignores; notes | no |

"Critical" means the advisory database said CRITICAL
(`database_specific.severity` in OSV, `severity` in npm and Dependabot); the
script never infers it from a CVSS vector.

# Step 3 — Triage

For each `secret`:

1. **Still in the tree, or history only?** `working tree` or a commit hash
   says which. History only is still public if the repo is, or ever was.
2. **Is it real?** A Firebase `AIza…` key in `google-services.json` is meant to
   ship in the app, and is restricted in the console instead. A fixture value
   in a test is fake. Either way, check before you allowlist.
3. **Real and pushed:** rotate it first, then think about rewriting history.
   Rewriting does not unpublish a key.
4. **False positive:** add its fingerprint, or `path:<glob>`, to
   `.security-sweep-allowlist` at that repo's root, with a `#` comment saying
   why.

For advisories, say whether the vulnerable code path is reachable (a dev-only
tool, a server-only route, a build plugin) before ranking it.

# Step 4 — Report

To the owner, in the conversation: each finding to act on with the repo, the
path and commit, the masked value, why it matters and the fix. Never paste a
finding from a real repository into a file in a public repository, and never
unmask a value — the fingerprint is enough to find it again with the script.
