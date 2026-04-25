# Mac Setup — Full Configuration

> ⚠️ **Note for lillorepo:** This guide was copied from a corporate (Retrofit/MasOrange) environment. Sections covering Kubernetes clusters, Oracle DB, enterprise Jira, masmovil email accounts, and `mm-monorepo` are **not applicable** to this project. Use what is relevant (Homebrew, shell, git, gcloud, Docker, AI tools) and ignore the rest.

Guide for setting up a new Mac with all team tools.

> You can use the `/mac-setup` command in Claude Code to run the setup interactively and guided.
> Reference files are in `docs/setup/`: `Brewfile`, `zshrc.template`, and `secrets.template`.

---

## Before You Start

### If you are coming from a previous Mac

If you have access to the previous Mac, run the backup script first:

```bash
bash tools/backup-mac.sh backup
```

This copies to `private/mac-backup/` (git-ignored): secrets, tokens, Claude config, MCPs, Oracle tnsnames, and DBeaver connections. Take that directory to the new Mac (Google Drive, USB, etc.) along with the repo.

On the new Mac, once you have the repo:

```bash
bash tools/backup-mac.sh restore
```

This restores: `.zshrc.secrets`, `github.pat`, `jira.pat`, `.mcp-atlassian.env`, `.mcp-atlassian-cloud.env`, `.mcp-slack.env`, `.claude/settings.json`, `.claude.json`, Claude memory, Oracle `tnsnames.ora`, and DBeaver `data-sources.json`.

> **DBeaver passwords:** passwords are in the macOS Keychain and **are not portable**. Connections will appear but you will need to re-enter the password the first time you connect to each one.

### If it is a completely new Mac (no backup)

The minimum needed to start working:

1. Install **Chrome** (required to authenticate with gcloud)
2. Install **Slack** (to recover Jira/Atlassian tokens if not saved)
3. Copy the repo to the Mac (Google Drive, clone with HTTPS if no SSH yet, etc.)

---

## Steps Requiring Manual Intervention

These steps **cannot be automated** — you have to do them yourself in the terminal or browser:

| Step | Why it is manual |
|------|-----------------|
| `brew install --cask temurin@17` | Requires system password (interactive sudo) |
| `brew install --cask zoom` | Uses pkg installer — requires interactive sudo |
| Add SSH key to GitHub | Browser action (Settings → SSH keys) |
| `gcloud auth login` | Opens browser for OAuth authentication |
| `gh auth login` | Opens browser for OAuth authentication |
| `jira init` | Requires your Jira token interactively |
| Fill in `~/.zshrc.secrets` | Contains passwords/tokens — never automated |

---

## Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Add to PATH (Apple Silicon):

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
eval "$(/opt/homebrew/bin/brew shellenv)"
```

---

## Base Installation (brew bundle)

The fastest way is to use the Brewfile:

```bash
brew bundle --file=docs/setup/Brewfile --no-upgrade
```

This installs everything except `temurin@17`, which you need to install manually:

```bash
brew install --cask temurin@17
# will ask for your password
```

### Known quirks

**sops:** brew installs 3.12.x by default, which breaks the setup. After the bundle verify:

```bash
sops --version
```

If it shows 3.12.x, do a manual downgrade (no versioned formula in brew):

```bash
brew uninstall sops
curl -Lo /opt/homebrew/bin/sops \
  https://github.com/getsops/sops/releases/download/v3.9.1/sops-v3.9.1.darwin.arm64
chmod +x /opt/homebrew/bin/sops
sops --version  # should say 3.9.1
```

**ClaudeUsageTracker:** has its own tap, not in the main homebrew tap:

```bash
brew tap masorange/claudeusagetracker
brew install --cask masorange/claudeusagetracker/claudeusagetracker
```

---

## Keyboard and Mouse

### System Preferences (System Settings)

**Keyboard** (System Settings → Keyboard):

- Key repeat rate: **Fast** (slider to maximum)
- Delay until repeat: **Short** (slider to minimum)
- Adjust brightness in low light: **ON**
- Turn off backlight after inactivity: **Never**
- Press 🌐 key to: **Show Emoji & Symbols**
- Keyboard navigation: **ON** (moves focus between controls with Tab)

**Mouse** (System Settings → Mouse):

- Tracking speed: **Fast** (slider to maximum)
- Natural scrolling: **ON**
- Secondary click: **Click Right Side**
- Smart zoom: **ON**

### iTerm2: terminal key bindings

Add in **iTerm2 → Settings → Keys → Key Bindings** (click `+`) with **Global** scope:

| Shortcut | Action | Value | Effect |
|----------|--------|-------|--------|
| `⌥ ←` | Send Escape Sequence | `b` | Move cursor one word backward |
| `⌥ →` | Send Escape Sequence | `f` | Move cursor one word forward |
| `⌘ ⌫` | Send Hex Code | `0x15` | Delete from cursor to beginning of line |
| `⌥ ⌫` | Send Hex Code | `0x17` | Delete previous word |

---

## Shell Configuration

```bash
# Backup .zshrc if something already exists
[ -f ~/.zshrc ] && cp ~/.zshrc ~/.zshrc.backup.$(date +%Y%m%d)

# Generate from template (replace USERNAME and EMAIL)
sed "s/{{USERNAME}}/$(whoami)/g; s/{{MASMOVIL_EMAIL}}/your.email@example.com/g" \
  docs/setup/zshrc.template > ~/.zshrc
```

Verify no placeholders remain:

```bash
grep "{{" ~/.zshrc  # should return nothing
```

If you don't have a backup of `.zshrc.secrets`, create one from the template:

```bash
cp docs/setup/secrets.template ~/.zshrc.secrets
chmod 600 ~/.zshrc.secrets
# edit manually with your real tokens
```

---

## git + ssh

New Mac = new SSH key. GitHub allows multiple keys per account.

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
git config --global init.defaultBranch main

# generate new key
ssh-keygen -t ed25519 -C "your.email@example.com"
cat ~/.ssh/id_ed25519.pub | pbcopy
```

Paste the key in GitHub: **Settings → SSH and GPG keys → New SSH key**.

Then register GitHub in known_hosts and verify:

```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts
ssh -T git@github.com
# should respond: Hi <user>! You've successfully authenticated...
```

```bash
gh auth login
# follow the prompts, opens the browser
```

---

## Google Cloud

```bash
# authenticate (opens browser)
gcloud auth login

# install gke plugin
gcloud components install gke-gcloud-auth-plugin --quiet

# configure docker for artifact registry
gcloud auth configure-docker europe-docker.pkg.dev
```

> **Note:** if `gcloud` fails with "python3.9: No such file or directory", verify that `~/.zshrc` has `CLOUDSDK_PYTHON="/opt/homebrew/bin/python3"` (not python3.9).

---

## Docker (colima)

```bash
colima start
docker ps  # verify
```

---

## Optional Tools

```bash
# intellij idea community (java)
brew install --cask intellij-idea-ce

# visual studio code
brew install --cask visual-studio-code

# bruno (api testing, postman alternative)
brew install --cask bruno

# dbeaver (universal sql client)
brew install --cask dbeaver-community

# the unarchiver (decompressor with more format support than native)
brew install --cask the-unarchiver

# granola (automatic AI meeting notes — https://www.granola.ai)
brew install --cask granola

# caffeine (prevents Mac from sleeping)
brew install --cask caffeine

# telegram
brew install --cask telegram
```

> **zoom:** requires interactive `sudo` (pkg installer), cannot be installed from brew bundle or unattended scripts. Install manually:
> ```bash
> brew install --cask zoom
> ```

---

## Final Verification

```bash
git --version && gh --version
docker --version
gcloud --version | head -1
python3 --version
[ -f ~/.zshrc.secrets ] && echo "zshrc.secrets OK" || echo "MISSING zshrc.secrets"
```

---

## Directory Structure

```bash
mkdir -p ~/Projects
mkdir -p ~/.local/bin
```

---

## AI Tools

- AI agent setup: [ai/claude-code-setup.md](ai/claude-code-setup.md)
- Token reduction proxy: [ai/rtk-setup.md](ai/rtk-setup.md)
- Pi coding agent: [ai/pi-setup.md](ai/pi-setup.md)
