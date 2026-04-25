# Pi Coding Agent Setup - MasOrange

> Requirements: Node.js 20+ on macOS, `jq` installed (`/usr/bin/jq`)

Pi is a minimal terminal coding harness by [@mariozechner](https://github.com/badlogic/pi-mono) that supports multiple providers (Anthropic, OpenAI/Codex, Google, etc.) and is highly extensible via skills, prompt templates, and extensions.

## 1. Install Pi

```bash
npm install -g @mariozechner/pi-coding-agent
pi --version
```

## 2. Configure Providers

All provider credentials live in `~/.pi/agent/auth.json`. Pi supports three key formats:

- **Env var name** — reads the named variable at startup
- **Shell command** — `"!command"` runs and uses stdout (cached per session)
- **Literal value** — used directly

### Anthropic (Claude)

Reads the token from `ANTHROPIC_AUTH_TOKEN` already set in `~/.zshrc.secrets`:

```json
"anthropic": { "type": "api_key", "key": "ANTHROPIC_AUTH_TOKEN" }
```

### Google (Gemini)

Reads `GEMINI_API_KEY` from `~/.zshrc.secrets`:

```json
"google": { "type": "api_key", "key": "GEMINI_API_KEY" }
```

### OpenAI Codex (GPT-5.x)

Pi's `/login` OAuth flow does not request the scopes required by business/SSO accounts
(`api.connectors.read`, `api.connectors.invoke`). The workaround is to borrow the
access token from the Codex CLI, which does obtain the correct scopes and auto-refreshes:

```json
"openai-codex": { "type": "api_key", "key": "!jq -r '.tokens.access_token' ~/.codex/auth.json" }
```

Prerequisite: Codex CLI must be installed and authenticated (`codex` → sign in). See [codex-setup.md](codex-setup.md).

### Full `~/.pi/agent/auth.json`

```json
{
  "anthropic": { "type": "api_key", "key": "ANTHROPIC_AUTH_TOKEN" },
  "google":    { "type": "api_key", "key": "GEMINI_API_KEY" },
  "openai-codex": { "type": "api_key", "key": "!jq -r '.tokens.access_token' ~/.codex/auth.json" }
}
```

## 3. Route Providers Through The Internal Proxy

Anthropic and Google must be routed through the internal MasOrange endpoint. Create `~/.pi/agent/models.json`:

```json
{
  "providers": {
    "anthropic": {
      "baseUrl": "https://llm.tools.cloud.masorange.es"
    },
    "google": {
      "baseUrl": "https://llm.tools.cloud.masorange.es"
    }
  }
}
```

OpenAI Codex goes directly to `api.openai.com` (no proxy needed).

## 4. Set Default Model And Scoped Models

Edit `~/.pi/agent/settings.json`:

```json
{
  "defaultProvider": "openai-codex",
  "defaultModel": "gpt-5.4",
  "enabledModels": [
    "openai-codex/gpt-5.4",
    "anthropic/claude-sonnet-4-6",
    "google/gemini-3.1-pro-preview"
  ]
}
```

`enabledModels` defines which models cycle with `Ctrl+P` / `Shift+Ctrl+P` inside pi.

### Available Models (as of 2026-04)

| Provider | Model | Notes |
|----------|-------|-------|
| `openai-codex` | `gpt-5.4` | Latest Codex, 272K context, thinking |
| `anthropic` | `claude-sonnet-4-6` | Latest Sonnet, 1M context, thinking |
| `anthropic` | `claude-opus-4-6` | Heaviest Claude, 1M context |
| `google` | `gemini-3.1-pro-preview` | Latest Gemini Pro |
| `google` | `gemini-2.5-flash` | Fast/cheap Gemini |

## 5. Verify Installation

```bash
# All providers
pi --provider openai-codex  --model gpt-5.4              -p "say hi"
pi --provider anthropic     --model claude-sonnet-4-6    -p "say hi"
pi --provider google        --model gemini-3.1-pro-preview -p "say hi"

# List models by provider
pi --list-models | grep anthropic
pi --list-models | grep openai-codex
pi --list-models | grep google
```

## 6. Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+L` | Open model picker (all models) |
| `Ctrl+P` | Cycle forward through scoped models |
| `Shift+Ctrl+P` | Cycle backward through scoped models |
| `Shift+Tab` | Cycle thinking level |
| `Ctrl+C` twice | Quit |
| `/model` | Switch model via command |

## 7. Repository Integration

Pi auto-loads `AGENTS.md` and `CLAUDE.md` from the project directory — no extra config needed in `retrofit`.

Skills are not auto-loaded; reference them explicitly:

```bash
pi --skill .agents/skills/review-pr/SKILL.md "Review the open PRs"
```

## 8. Configuration File Reference

| File | Purpose |
|------|---------|
| `~/.pi/agent/auth.json` | API keys and OAuth tokens per provider |
| `~/.pi/agent/models.json` | Provider base URL overrides and custom models |
| `~/.pi/agent/settings.json` | Default provider/model, scoped models, UI settings |
| `.pi/settings.json` | Project-level overrides (checked into repo) |

## 9. Useful References

- Repo: https://github.com/badlogic/pi-mono
- npm: https://www.npmjs.com/package/@mariozechner/pi-coding-agent
- Local docs: `$(npm root -g)/@mariozechner/pi-coding-agent/docs/`

## Related Guides

- [claude-code-setup.md](claude-code-setup.md)
- [codex-setup.md](codex-setup.md)
- [gemini-cli-setup.md](gemini-cli-setup.md)
