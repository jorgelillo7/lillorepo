# Claude Code Setup - MasOrange

> Requirements: Apple Silicon Mac recommended

This guide installs Claude Code, configures the local environment, and points to the Claude-specific MCP and RTK guides used in `retrofit`.

## 1. Install Claude Code

```bash
brew install --cask claude-code
npm install -g @anthropic-ai/claude-code
```

Official reference:

- https://docs.anthropic.com/en/docs/claude-code

## 2. Get Your API Key

1. Contact `@jorge.lillo` on Slack.
2. Request your personal API key.
3. Expect it to expire every 90 days.

## 3. Configure Environment Variables

Add these variables to `~/.zshrc`:

```bash
export ANTHROPIC_AUTH_TOKEN=sk-XXXXXXXX
export ANTHROPIC_BASE_URL=https://llm.tools.cloud.masorange.es
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

Repository:

- https://github.com/masorange/ClaudeUsageTracker

Install with Homebrew:

```bash
brew tap masorange/claudeusagetracker
brew install --cask masorange/claudeusagetracker/claudeusagetracker
```

Update later with:

```bash
brew update && brew upgrade --cask masorange/claudeusagetracker/claudeusagetracker
```

## 6. Verify Installation

```bash
claude --version
echo $ANTHROPIC_AUTH_TOKEN
echo $ANTHROPIC_BASE_URL
```

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

## 8. Available Tools In Retrofit

Claude Code is expected to use:

- `gh` for GitHub workflows
- `kubectl` for Kubernetes operations
- `jira-masorange` MCP for Jira and Confluence
- `slack-masorange` MCP for Slack
- `oracle-mysim-sta` for STA database access
- `oracle-mysim-pro` for PROD database access with explicit confirmation
- `oracle-mos` for Oracle My Support knowledge lookup

### Rules worth remembering

- Always verify the active Kubernetes context before running `kubectl`.
- Read [`CLAUDE.md`](../../../CLAUDE.md) before touching Oracle PROD.
- Use the Claude-specific MCP guide for all `claude mcp` commands.

## 9. Configure MCP Servers

Use the dedicated Claude guide:

- [mcp-setup-claude-code.md](mcp-setup-claude-code.md)

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

- [codex-setup.md](codex-setup.md)
- [mcp-setup.md](mcp-setup.md)
- [mcp-setup-codex.md](mcp-setup-codex.md)
