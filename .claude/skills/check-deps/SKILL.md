---
name: check-deps
description: Snapshot the project's critical pinned versions (Bazel, Python, Bazel modules, GitHub Actions, key Python libs) and compare against today's latest releases. Output a prioritised upgrade list — urgent vs recommended vs up-to-date.
model-invocable: false
allowed-tools:
  - Bash
  - WebFetch
  - WebSearch
  - Read
---

# Goal

Audit what versions the project pins for its critical dependencies, look up
the latest release of each one, and tell the user which upgrades are urgent
(security, EOL, deprecation) vs nice-to-have vs already current.

# Step 1 — Snapshot current versions

Run the helper script to dump the current pinned versions:

```bash
bash .claude/skills/check-deps/check_deps.sh
```

The script reads from the canonical sources of truth:

- `.bazelversion` for the Bazel CLI
- `MODULE.bazel` for Python toolchain version and `bazel_dep` modules
- `.github/workflows/*.yml` for GitHub Actions versions
- `core/requirements.txt` and `packages/*/*/requirements.txt` for direct deps
- `requirements_lock.txt` for the resolved version of each critical library

Show the output to the user as-is — that is part 1 of the answer.

# Step 2 — Look up latest stable releases

For each line in the snapshot, fetch the latest stable version. Use **WebFetch**
on the canonical release page; only fall back to **WebSearch** if WebFetch can't
get a definitive answer.

Canonical sources (use these — do not guess):

| Item | URL |
|------|-----|
| Bazel | `https://github.com/bazelbuild/bazel/releases/latest` |
| Python | `https://www.python.org/downloads/` |
| `rules_python` | `https://github.com/bazelbuild/rules_python/releases/latest` |
| `rules_oci` | `https://github.com/bazel-contrib/rules_oci/releases/latest` |
| `rules_pkg` | `https://github.com/bazelbuild/rules_pkg/releases/latest` |
| `platforms` | `https://github.com/bazelbuild/platforms/releases/latest` |
| `actions/checkout`, `actions/setup-python`, etc. | `https://github.com/<owner>/<repo>/releases/latest` |
| `bazel-contrib/setup-bazel` | `https://github.com/bazel-contrib/setup-bazel/releases/latest` |
| `dorny/paths-filter` | `https://github.com/dorny/paths-filter/releases/latest` |
| `google-github-actions/auth`, `setup-gcloud` | `https://github.com/google-github-actions/<repo>/releases/latest` |
| Python libs (Flask, requests, etc.) | `https://pypi.org/pypi/<package>/json` (or the project page) |

Be efficient: fetch in parallel where possible. For **GitHub Actions versions
that pin to a major like `v4`**, the relevant comparison is whether a `v5`
exists — if `v4` is still the latest major, treat it as up-to-date.

# Step 3 — Classify each item

For each dependency, decide one of three buckets and explain why:

- 🔴 **Urgent** — bump should happen soon. Triggers any of:
  - Pinned version is past or near End-of-Life / security-only.
  - A known CVE affecting the pinned version was fixed in a later one.
  - The current major is unsupported by tooling we depend on.
  - The pin is multiple majors behind and the gap is widening fast.
- 🟡 **Recommended** — would be nice to bump:
  - One or two minor versions behind, no security concern.
  - The new version unlocks features we'd plausibly use (mention which).
- 🟢 **Up-to-date** — at or within one minor of latest stable, no action needed.

For each 🔴 / 🟡 item include:
- Current version → latest version
- One-line reason
- Concrete cost: which files have to change in lockstep (e.g. "MODULE.bazel +
  Dockerfile.base + workflow Python step + regenerate `requirements_lock.txt`")

For 🟢 items just one line: `<name>: X.Y (latest) ✓`.

# Step 4 — Final output

Structure the response in three sections in this order:

1. **Snapshot** — the script output verbatim.
2. **Compared with latest** — the classified list, urgent first.
3. **Recommendation** — a short prose paragraph: which 1-3 things to bump now,
   which to schedule, which to ignore. End with the concrete next-step command
   if there's a clear winner (e.g. "bump `actions/checkout` to v5 in
   `.github/workflows/deploy.yml`").

# Rules

- The script is the source of truth for *current* versions. Don't paraphrase or
  re-derive what's pinned.
- Don't recommend bumps that aren't actually justified. "Newer = always upgrade"
  is the wrong heuristic; reproducibility costs are real.
- Don't open PRs or edit files. This skill is read-only — analysis only.
- If a fetch fails or returns ambiguous results, say so explicitly rather than
  guessing.
