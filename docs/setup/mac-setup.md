# Mac Setup

Getting a Mac ready to build, test and deploy lillorepo.

> This guide used to carry a corporate environment's setup — Kubernetes, Oracle
> DB, enterprise Jira, `sops`, Temurin — and pointed at reference files
> (`Brewfile`, `zshrc.template`, `secrets.template`, `tools/backup-mac.sh`) that
> never existed in this repo, so half its commands failed if you ran them. It is
> now scoped to what this repo actually needs. The old content is in
> `git log -- docs/setup/mac-setup.md` if you ever want it back.

---

## Steps that cannot be automated

| Step | Why it is manual |
|------|-----------------|
| Add SSH key to GitHub | Browser action (Settings → SSH keys) |
| `gcloud auth login` | Opens a browser for OAuth |
| `gh auth login` | Opens a browser for OAuth |

Everything else below is scriptable.

---

## 1. Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
eval "$(/opt/homebrew/bin/brew shellenv)"
```

## 2. Everything else, in one command

```bash
brew bundle --file=docs/setup/Brewfile --no-upgrade
```

[`Brewfile`](Brewfile) holds what the repo needs and nothing personal. Check
what is missing without installing anything:

```bash
brew bundle check --file=docs/setup/Brewfile --verbose
```

> **`google-cloud-sdk`:** if you already installed gcloud with Google's own
> installer, skip that line — two copies on the `PATH` shadow each other and
> the failure is confusing.

## 3. git and SSH

A new Mac means a new SSH key; GitHub accepts several per account.

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

ssh-keygen -t ed25519 -C "your.email@example.com"
pbcopy < ~/.ssh/id_ed25519.pub
```

Paste it into **GitHub → Settings → SSH and GPG keys → New SSH key**, then:

```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts
ssh -T git@github.com     # "Hi <user>! You've successfully authenticated"
gh auth login
```

> Use brew's `git`, not Xcode's. Apple ships a build years behind — a fresh
> machine reported `2.39.3 (Apple Git-146)`, from 2022.

## 4. Google Cloud

This repo deploys to **two** projects. `biwenger-tools` is the default;
`be_water` overrides it per service, so you do not need to switch.

```bash
gcloud auth login
gcloud config set project biwenger-tools
gcloud auth configure-docker europe-southwest1-docker.pkg.dev
```

> If gcloud fails with "python3.9: No such file or directory", set
> `CLOUDSDK_PYTHON="/opt/homebrew/bin/python3"` in `~/.zshrc`.

## 5. Terminal tools worth wiring up

Installed by the Brewfile, but each needs one step before it does anything.

**fzf** — fuzzy `Ctrl-R`. The reason it pays off here is that this repo's daily
commands are long and near-identical (`gcloud run services list --project …
--region … --format=…`), and hunting for them with arrow keys is the tax.

```bash
$(brew --prefix)/opt/fzf/install    # adds one line to ~/.zshrc, rebinds ^R and ^T
```

**git-delta** — syntax-highlighted, word-level diffs. It hooks into git itself,
so every `git diff`, `git show` and `git log -p` improves without changing how
you invoke them.

```bash
git config --global core.pager delta
git config --global interactive.diffFilter "delta --color-only"
git config --global delta.navigate true
git config --global delta.line-numbers true
git config --global merge.conflictstyle zdiff3
```

**byobu** — keeps a long session alive across a dropped connection or a closed
window. See [`long-running-sessions.md`](long-running-sessions.md), which also
covers sleep.

**ripgrep** — `rg` honours `.gitignore`, so it skips the `bazel-*` symlink farms
that make `grep -r` slow and noisy here. Nothing to configure.

## 6. Keeping the Mac awake

Native, nothing to install:

```bash
caffeinate -i byobu     # awake only while that command runs
```

`keepingyouawake` (in the Brewfile) is the menu-bar equivalent if you prefer
clicking. **Do not install `caffeine`** — unmaintained and older than Apple
Silicon. Full reasoning in [`long-running-sessions.md`](long-running-sessions.md).

## 7. Secrets

Nothing in this repo needs a secrets file to build or test. Production secrets
live in Google Secret Manager; local runs read a per-module `.env` that is
git-ignored. See [`../operations.md`](../operations.md) → Secrets Management.

## 8. Verify

```bash
bazelisk --version          # launches the Bazel pinned in .bazelversion
gh --version && git --version
gcloud --version | head -1
docker --version
bazel test //core:core_tests    # the real proof: a green suite
```

---

## Keeping it current

Two skills audit versions, and they answer different questions:

| Skill | Audits |
|---|---|
| `check-deps` | what the **repo** pins — Bazel, Python, modules, Actions |
| `audit-mac-tools` | what the **machine** has installed |

## AI tools

- Surviving long agent runs: [`long-running-sessions.md`](long-running-sessions.md)
- Claude Code setup: [`ai/claude-code-setup.md`](ai/claude-code-setup.md)
- Token reduction proxy: [`ai/rtk-setup.md`](ai/rtk-setup.md)
- Pi coding agent: [`ai/pi-setup.md`](ai/pi-setup.md)
