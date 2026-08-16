---
name: audit-mac-tools
description: Audit the Mac's developer toolchain — what is installed, what is genuinely stale, what is abandoned upstream and should be replaced. Separates the tools this repo actually builds with from everything else, and filters the false positives `brew outdated --greedy` produces for self-updating apps.
model-invocable: false
allowed-tools:
  - Bash
  - WebFetch
  - WebSearch
  - Read
---

# Goal

Tell the user which of their installed tools are actually out of date, which
are abandoned and want replacing, and which look stale but are not.

This is the machine-level counterpart to `check-deps`, which audits what the
*project* pins. Nothing here touches the repo.

# The trap this skill exists for

**`brew outdated --cask --greedy` lies.** Homebrew only knows the version it
installed. An app that updates itself — VS Code, Docker Desktop, Discord,
Spotify, Telegram, Postman, JetBrains, Chrome — keeps updating quietly while
brew's record stays frozen at whatever it first put there. A real run reported
`visual-studio-code (1.61.2) != 1.133.0`, a four-year gap, on a machine
actually running 1.130.0.

Reporting those as "out of date" sends the user to reinstall apps that are
fine, and buries the handful that genuinely matter.

**Always confirm a cask's real version from the app bundle before reporting
it**:

```bash
defaults read "/Applications/<App>.app/Contents/Info.plist" CFBundleShortVersionString
```

If the bundle version is current, the item is 🟢 — say brew's record is stale
and move on. Only `brew upgrade --cask <name>` if the user wants brew's
bookkeeping fixed, which is cosmetic.

# Step 1 — Snapshot

```bash
brew outdated --formula --verbose
brew outdated --cask --verbose --greedy
brew list --cask
```

Then the tools this repo builds and ships with, from the machine itself — not
from brew's record:

```bash
bazelisk --version; buildifier --version; gh --version
python3 --version; git --version; claude --version
gcloud --version | head -3
```

# Step 2 — Split into three groups

Order the report by what breaks if it is wrong, not alphabetically.

1. **Toolchain this repo depends on** — `bazelisk`, `buildifier`, `gh`,
   `gcloud`, `python3`, `git`, `claude`. A stale one here costs build time or
   CI parity.
2. **System libraries with a security surface** — `ca-certificates`, `openssl`,
   `curl`, `libpng`/`libtiff`/`freetype` and friends. `ca-certificates` is the
   one that bites hardest and quietest: a stale bundle makes HTTPS calls fail
   with `CERTIFICATE_VERIFY_FAILED` against perfectly valid sites, and the
   error blames the site.
3. **Everything else** — apps. Mostly noise; report only the genuinely stale
   ones after the bundle-version check above.

# Step 3 — Check for abandonment, not just staleness

A tool at its latest version can still be the wrong tool. For anything that
looks unmaintained, check the last upstream release date and whether the
ecosystem has moved on. Known cases in this repo's history:

| Abandoned | Replacement |
|---|---|
| `caffeine` (cask) | native `caffeinate -i`, or Amphetamine / KeepingYouAwake — see [`docs/setup/long-running-sessions.md`](../../../docs/setup/long-running-sessions.md) |

When a formula's last release predates Apple Silicon, say so — it is a
stronger signal than a version gap.

# Step 4 — Classify

- 🔴 **Fix now** — security-relevant (expired CA bundle, an unpatched CVE), or
  a build tool far enough behind to diverge from CI.
- 🟡 **Worth doing** — a real gap with a concrete benefit; name the benefit.
- ⚫️ **Replace** — abandoned upstream; name the replacement.
- 🟢 **Fine** — including "brew's record is stale, the app is current".

# Step 5 — Output

1. **What is installed** — the toolchain versions, verbatim.
2. **Findings** — grouped by the three buckets, 🔴 first, each with current →
   latest and a one-line reason.
3. **The commands** — a copy-pasteable block for the 🔴 and 🟡 items only.

# Rules

- **Never report a `--greedy` cask without checking the bundle version.** That
  check is the entire value of this skill.
- Do not run `brew upgrade` — this skill is read-only. Hand the user the
  commands and let them choose.
- `brew upgrade` with no arguments upgrades everything, including things the
  user pinned deliberately. Always name the formulae explicitly.
- Do not recommend upgrading a tool the repo pins on purpose. Check
  `MODULE.bazel` / `.bazelversion` before calling a build tool stale — the
  version in CI is the one that matters.
- Verify version claims. Never state "X is the latest" from memory; fetch it.
