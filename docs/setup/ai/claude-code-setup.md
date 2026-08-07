# Claude Code Setup

> Requirements: Apple Silicon Mac recommended

This guide installs Claude Code, configures the local environment, and points to the Claude-specific MCP and RTK guides.

## 1. Install Claude Code

Pick **one** method. Installing via Homebrew *and* npm leaves two `claude`
binaries competing on the `PATH`, and they drift to different versions.

**Homebrew (recommended):**

```bash
brew install --cask claude-code@latest
```

Use the `@latest` cask, not `claude-code`. The plain `claude-code` cask tracks
the stable channel and lags several releases behind; a client that is too old
simply does not offer the newest models in the selector.

**npm (alternative):**

```bash
npm install -g @anthropic-ai/claude-code
```

### Keeping it updated

A Homebrew install **disables Claude Code's own auto-updater** — brew owns the
binary, so you stay pinned to whatever the cask ships until you upgrade it
yourself:

```bash
brew update && brew upgrade --cask claude-code@latest
```

`brew update` refreshes the cask definitions; without it `brew upgrade`
compares your version against a stale catalogue and reports you are up to date
when you are not. To check first without installing anything:

```bash
brew outdated --cask claude-code@latest
```

The npm install self-updates, so it needs no equivalent step.

Official reference:

- https://docs.anthropic.com/en/docs/claude-code

## 2. Get Your API Key

1. Contact `@jorge.lillo` on Slack.
2. Request your personal API key.
3. Expect it to expire every 90 days.

## 3. Configure Environment Variables — corporate gateway only

> **Do not set these on a personal machine.** They route every request through
> the corporate gateway, which exposes only the models that gateway allows, and
> `ANTHROPIC_DEFAULT_SONNET_MODEL` pins one model by hand. The symptom is a
> model selector missing the newest models — indistinguishable from running an
> outdated client. On a personal setup all `ANTHROPIC_*` variables must stay
> unset so Claude Code uses your own account and its full model roster.

Add these variables to `~/.zshrc`:

```bash
export ANTHROPIC_AUTH_TOKEN=sk-XXXXXXXX
export ANTHROPIC_BASE_URL=https://llm.gateway.internal.example.com
export ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-4-6
export CLAUDE_CODE_USE_VERTEX=0
```

Apply the changes:

```bash
source ~/.zshrc
```

## 4. Install The VS Code Extension

1. Open Visual Studio Code.
2. Open Extensions with `Cmd+Shift+X`.
3. Search for `Claude Code for VS Code`.
4. Install the official extension.

## 5. Install Usage Monitoring

If your organisation ships a usage tracker, install it here — they are
normally distributed as a private Homebrew tap. Nothing in this repo
depends on one.

## 6. Verify Installation

```bash
which -a claude   # must print exactly one path
claude --version
echo $ANTHROPIC_AUTH_TOKEN
echo $ANTHROPIC_BASE_URL
```

More than one line from `which -a claude` means both installation methods are
present. Remove one — `brew uninstall --cask claude-code` /
`brew uninstall --cask claude-code@latest`, or
`npm uninstall -g @anthropic-ai/claude-code` — and reopen the shell.

On a personal machine the two `echo` lines must come back empty (see section 3).

## 7. Configure The Custom Status Line

Copy the status line script from the repository:

```bash
cp .claude/hooks/global/statusline.sh ~/.claude/statusline.sh
chmod +x ~/.claude/statusline.sh
```

Create `~/.claude/settings.json` if needed:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.sh",
    "padding": 0
  }
}
```

Verify it:

```bash
ls -l ~/.claude/statusline.sh
cat ~/.claude/settings.json
echo '{"model":{"display_name":"Sonnet 4.5"},"context_window":{"used_percentage":15},"cost":{"total_cost_usd":0.0234}}' | ~/.claude/statusline.sh
```

Official status line reference:

- https://code.claude.com/docs/en/statusline

## 8. Available Tools In A Corporate Setup

Claude Code is expected to use:

- `gh` for GitHub workflows
- `kubectl` for Kubernetes operations
- a Jira/Confluence MCP
- a Slack MCP
- `oracle-staging` for staging database access
- `oracle-prod` for production database access with explicit confirmation
- an Oracle support knowledge-base lookup

### Rules worth remembering

- Always verify the active Kubernetes context before running `kubectl`.
- Read [`CLAUDE.md`](../../../CLAUDE.md) before touching Oracle PROD.
- Use the Claude-specific MCP guide for all `claude mcp` commands.

## 9. Configure MCP Servers

See [mcp-setup.md](mcp-setup.md) for how MCP wiring differs by client.

## 10. Configure RTK

RTK is highly recommended because it reduces noisy terminal output before Claude sees it.

Quick install:

```bash
brew install rtk
rtk init --global
```

This registers the Claude hook in `~/.claude/settings.json`.

See the full guide:

- [rtk-setup.md](rtk-setup.md)

## Related Guides

- [mcp-setup.md](mcp-setup.md)
- [rtk-setup.md](rtk-setup.md)
