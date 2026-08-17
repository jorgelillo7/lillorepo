---
name: audit-mac-tools
description: Audit the Mac's developer toolchain — what is installed, what is genuinely stale, what is abandoned upstream and should be replaced — then suggest tools worth adopting based on what is already there. Writes a dated report to reports/ and filters the false positives `brew outdated --greedy` produces for self-updating apps.
model-invocable: false
allowed-tools:
  - Bash
  - WebFetch
  - WebSearch
  - Read
  - Write
---

# Goal

Tell the user which of their installed tools are actually out of date, which
are abandoned and want replacing, which look stale but are not — and what is
worth adopting given how they already work.

This is the machine-level counterpart to `check-deps`, which audits what the
*project* pins. Nothing here touches the repo's own dependencies.

# Where the report goes, and why it is git-ignored

Write the report to `reports/YYYY-MM-DD.md` **inside this skill's directory**.
`reports/` is in `.gitignore` and must stay there.

**lillorepo is a public repository.** A full inventory of installed software
with versions is reconnaissance: it tells anyone reading exactly which
outdated builds this machine runs. The report is for its owner, not for
GitHub. If a future edit moves it somewhere tracked, that is a regression, not
a tidy-up.

# NEVER upgrade the app hosting this session

Upgrading an app quits it. If that app is the one the agent is running inside,
the upgrade kills the session mid-command — the tool call comes back as exit
code 137 and everything after it is lost.

This has happened. A session running in VS Code's integrated terminal ran
`brew upgrade --cask visual-studio-code` and killed itself, one turn after
writing a guide about keeping long sessions alive.

**Detect the host before touching any cask:**

```bash
echo "$TERM_PROGRAM"          # vscode | iTerm.app | Apple_Terminal
ps -o comm= -p $PPID          # walk up if unsure
```

| `TERM_PROGRAM` | Never upgrade |
|---|---|
| `vscode` | `visual-studio-code`, `cursor`, `windsurf` |
| `iTerm.app` | `iterm2` |
| `Apple_Terminal` | (Terminal.app is not a cask — safe) |

Exclude the host from every upgrade command, list it separately under **"do
this yourself"**, and say why. If the user insists, tell them to run it from a
different terminal app, or from inside `byobu` — tmux's server is detached
from the terminal that started it, so the session survives the host quitting.

The same applies to any app the session depends on: never upgrade the terminal
emulator you are printing to.

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

# Step 2 — Split into groups, and keep dev separate from the rest

Order the report by what breaks if it is wrong, not alphabetically. Tag every
item **`[dev]`** or **`[personal]`** and never mix them in one command: the
first group affects whether this repo builds, the second is housekeeping the
user may not want touched at all.

1. **`[dev]` Toolchain this repo depends on** — `bazelisk`, `buildifier`,
   `gh`, `gcloud`, `python3`, `git`, `claude`, plus the terminal tools the
   workflow leans on (`fzf`, `git-delta`, `ripgrep`, `byobu`, `jq`). A stale
   one here costs build time or CI parity.
2. **`[dev]` System libraries with a security surface** — `ca-certificates`,
   `openssl`, `curl`, `libpng`/`libtiff`/`freetype` and friends.
   `ca-certificates` is the one that bites hardest and quietest: a stale
   bundle makes HTTPS calls fail with `CERTIFICATE_VERIFY_FAILED` against
   perfectly valid sites, and the error blames the site.
3. **`[personal]` Everything else** — media players, chat clients, IDEs,
   database GUIs. Nothing here affects the repo. Report only the ones that are
   genuinely stale after the bundle-version check, and never upgrade them
   without being asked: a major version of a GUI app can migrate a profile or
   change a workflow, which is the user's call and not a maintenance detail.

The Brewfile is the reference for what counts as `[dev]`:
[`docs/setup/Brewfile`](../../../docs/setup/Brewfile). Anything installed but
absent from it is `[personal]` by definition.

## Orphaned cask records

An app deleted by dragging it to the Trash leaves brew's record behind, and it
then reports as outdated forever. The symptom is
`Error: <name>: It seems the App source '/Applications/<App>.app' is not there.`

Do not treat these as upgrades. List them as **orphans** and offer the
cleanup, which removes only brew's bookkeeping:

```bash
brew uninstall --cask --force <name>
```

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

# Step 5 — Suggest what is worth adopting

The audit answers "what is broken". This step answers "what is missing", and
it is the part with actual judgement in it.

**Derive suggestions from the inventory, not from a list of popular tools.**
Read what is installed and infer how the user works, then propose the few
things that fit that. Concretely, look for:

- **A gap next to something already relied on.** They use `gh` heavily but
  have no `git-delta`; they run Bazel but have no `bazel-watcher`. The
  adjacency is the argument.
- **A modern replacement for something being tolerated.** Not novelty for its
  own sake — only when the replacement is meaningfully better *for their use*,
  and say what specifically.
- **Something the repo's own workflows imply.** If `docs/` or a runbook
  describes doing a thing by hand that a tool automates, that is a real find.
- **What they already tried and dropped.** A cask installed and never updated
  since 2021 is a tool that did not stick. Do not re-recommend it.

Rules for this section, because it is the easiest place to waste the user's
time:

- **Three suggestions maximum**, ranked. A long list is ignored wholesale.
- Each one states: what it does, *why it fits this machine specifically*, the
  install command, and the honest cost (another daemon, another config file,
  another thing to keep updated).
- **Confirm the tool is alive** before suggesting it — check the last release.
  Recommending an abandoned tool in the same report that flags abandoned tools
  is self-defeating.
- If nothing genuinely fits, **say nothing fits**. "Your setup is complete for
  what you do" is a valid and useful answer, and far better than padding.
- Never suggest something that duplicates what is installed and working.

# Step 6 — Output

Write the report to `reports/YYYY-MM-DD.md` and summarise it in chat. Both
carry the same four sections:

1. **What is installed** — the toolchain versions, verbatim.
2. **Findings** — grouped by the buckets above, 🔴 first, each tagged `[dev]`
   or `[personal]`, with current → latest and a one-line reason.
3. **The commands** — **three separate blocks**, never one:

   ```bash
   # [dev] — affects whether this repo builds
   brew upgrade <formulae>

   # [personal] — housekeeping, only if you want it
   brew upgrade --cask <apps>

   # do this yourself: upgrading these quits the session
   brew upgrade --cask visual-studio-code
   ```

   The split is the point. Someone should be able to run the first block
   without thinking and leave the second for later.
4. **Worth adopting** — Step 5, or an explicit "nothing".

Overwrite the day's file if it already exists; keep older dates, they are the
history of what was stale when.

# Rules

- **Never upgrade the app hosting the session.** Check `TERM_PROGRAM` first.
  Exit code 137 mid-audit is this rule being broken.
- **Never report a `--greedy` cask without checking the bundle version.** That
  check is the entire value of this skill.
- Never bundle `[dev]` and `[personal]` upgrades into one command.
- A `brew upgrade --cask` of several apps **aborts the whole batch** on the
  first bad name (`Cask 'claude-code' is not installed` — the real name was
  `claude-code@latest`). Verify names against `brew list --cask` first, or run
  them one at a time so one typo does not skip the rest.
- Do not run `brew upgrade` — this skill is read-only. Hand the user the
  commands and let them choose.
- `brew upgrade` with no arguments upgrades everything, including things the
  user pinned deliberately. Always name the formulae explicitly.
- Do not recommend upgrading a tool the repo pins on purpose. Check
  `MODULE.bazel` / `.bazelversion` before calling a build tool stale — the
  version in CI is the one that matters.
- Verify version claims. Never state "X is the latest" from memory; fetch it.
- The report goes in `reports/` and nowhere else. It is git-ignored on
  purpose — see the note at the top.
