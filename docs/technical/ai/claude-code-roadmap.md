# Claude Code Roadmap — Summary and Audit

Source: [roadmap.sh/claude-code](https://roadmap.sh/claude-code) (published 2026-02-10, updated 2026-02-26)

---

## Roadmap Structure

The roadmap organises Claude Code into **5 main blocks** plus a sidebar cheatsheet of commands.

---

## 1. Introduction

Foundational concepts before using Claude Code.

| Topic | Description |
|-------|-------------|
| What is Vibe Coding? | Programming by describing what you want, without writing code line by line |
| What is a Coding Agent? | Agent that can read/write files, execute commands, and reason |
| What is Agentic Loop? | Reasoning → action → observation cycle that Claude follows |
| Setting up Claude | CLI installation, authentication, initial configuration |
| Subscription / API usage | Payment modes: Max subscription vs API with per-token billing |

**Ways to use Claude:**
- **Claude CLI** — terminal, main mode
- **Desktop App** — Claude.app with screen integration
- **Editor Extensions** — VSCode, JetBrains, etc.
- **Community Tools** — external tools built by the community

---

## 2. Understand the Basics

Concepts to master in order to work well with Claude Code.

| Concept | What it is |
|---------|------------|
| **AGENTS.md / CLAUDE.md** | Permanent instruction files; `CLAUDE.md` is the project entry point and canonical guide |
| **Skills** | Reusable commands; stored canonically in `.claude/skills/` |
| **Context** | Active context window; manage what goes in and what stays out |
| **Modes** | Operating modes: normal, plan, headless |
| **Models** | Opus (maximum quality), Sonnet (balance), Haiku (speed/cost) |
| **Tools** | Tools Claude can use: Read, Edit, Bash, Glob, Grep... |
| **MCP** | Model Context Protocol — external servers that extend capabilities |
| **Plugins** | Additional ecosystem integrations |
| **Hooks** | Scripts that run on Claude lifecycle events |
| **Subagents** | Specialised agents that run in parallel or in sequence |
| **Common Usecases** | Typical use cases: code review, debugging, documentation |

**When to use each model:**
- **Opus** — complex tasks, planning, architecture decisions
- **Sonnet** — general daily use (the most balanced)
- **Haiku** — quick responses, simple tasks, cost savings

---

## 3. Command Cheatsheet (sidebar)

### Shortcuts and Prefixes

| Shortcut / Prefix | Function |
|-------------------|---------|
| `Ctrl+C` | Interrupt generation |
| `Ctrl+R` | Search command history |
| `Esc` | Cancel current action |
| `Esc + Esc` | Return to clean prompt |
| `Shift+Tab` | Toggle tool auto-accept mode |
| `/` (slash) | Open slash commands menu |
| `!` prefix | Run shell command directly |
| `\` prefix | Multiline input |
| `@` prefix | Reference file or URL in the prompt |

### Claude CLI Commands

| Command | Function |
|---------|---------|
| `claude` | Start interactive session |
| `claude "query"` | Single question, no session |
| `claude -p` | Pipe mode (stdin → stdout, headless) |
| `claude -c` | Continue last session |
| `claude -r` | Resume/summarise session by ID |
| `claude --add-dir` | Add additional directory to context |

### Slash Commands in session

| Command | Category | Function |
|---------|----------|---------|
| `/help` | Info | General help |
| `/usage` | Info | View token usage in session |
| `/cost` | Info | View session cost |
| `/status` | Info | Session status |
| `/clear` | Session | Clear context (new session) |
| `/compact` | Session | Compact context (auto-summary) |
| `/context` | Session | View current context contents |
| `/memory` | Session | View persistent memory |
| `/init` | Session | Initialise CLAUDE.md in the project |
| `/exit` | Session | Exit |
| `/export` | Session | Export conversation |
| `/rewind` | Session | Revert to an earlier point |
| `/plan` | Workflow | Enter planning mode |
| `/doctor` | Debug | Environment diagnostics |
| `/config` | Config | Manage configuration |
| `/permissions` | Config | View/change permissions |
| `/model` | Config | Change active model |
| `/agents` | Config | Manage agents |
| `/hooks` | Config | Manage hooks |
| `/mcp` | Config | Manage MCP servers |

### Lifecycle Hooks

| Hook | When it fires |
|------|--------------|
| `SessionStart` | When a session starts |
| `SessionEnd` | When a session ends |
| `PreToolUse` | Before Claude uses a tool |
| `PostToolUse` | After using a tool |
| `UserPromptSubmit` | When a prompt is submitted |
| `Stop` | When Claude finishes responding |

---

## 4. Claude Workflow

How to work well with Claude Code day to day.

| Topic | Description |
|-------|-------------|
| **Permission Modes** | Default, auto-accept, read-only — control what Claude can do without confirmation |
| **Plan Mode** | Claude plans before executing; ideal for large changes |
| **Manage Sessions** | Conversation management: continue, resume, clear |
| **Resume** | `claude -r` to resume a previous session |
| **Rewind** | `/rewind` to undo actions within a session |

**Usage Best Practices** (highlighted yellow block):
- Be specific in prompts
- Use Plan Mode for complex tasks
- Compact context regularly
- Review before accepting destructive changes

---

## 5. CLAUDE.md

The most important file in the setup.

| Aspect | Description |
|--------|-------------|
| **How to Structure** | Project rules, team context, available tools, conventions |
| **Locations** | `~/.claude/CLAUDE.md` (global), `.claude/CLAUDE.md` or `CLAUDE.md` (project) |

In `lillorepo`, `CLAUDE.md` is the canonical project instruction file.

---

## 6. Skills

Custom reusable commands.

| Aspect | Description |
|--------|-------------|
| **Creating Skills** | In lillorepo, skills live in `.claude/skills/<name>/SKILL.md` |
| **Skill Best Practices** | Descriptive names, specific prompts, usage examples |

---

## 7. Subagents

Specialised agents for specific tasks.

| Aspect | Description |
|--------|-------------|
| **Creating Subagents** | File in `.claude/agents/<name>.md` with `name`, `description`, `model` |

---

## 8. Hooks

Automations on lifecycle events.

| Aspect | Description |
|--------|-------------|
| **Hook Events & Matchers** | Filter by event and by tool/pattern |
| **Hook Types** | `command` (shell), others |
| **Hook Inputs & Outputs** | JSON on stdin/stdout for communication with Claude |

---

## 9. Manage Context

Efficient context management to avoid degradation.

| Technique | When |
|-----------|------|
| **Understand Claude Pricing** | Know per-token cost for model decisions |
| **Use /compact and /clear** | Long context → compact; clean start → clear |
| **Be mindful of extensions** | Editor extensions consume additional context |
| **Use subagents and hooks** | Delegate parallel tasks to subagents |
| **Thinking modes & Effort** | Configure extended reasoning level (Sonnet/Opus) |
| **Prompt Caching** | Reuse common context between API calls to reduce cost |

---

## 10. Advanced Claude Code

### Customize Status Line
Customise the CLI status bar with session metrics.

### Connecting Tools with MCP
Extend Claude's capabilities with MCP servers:
- **Skills for MCP** — use skills as MCP tools

### Model Configuration
- **Opusplan** — use Opus for planning and Sonnet for execution

### Output Styles
Control response format (JSON, markdown, structured).

### Plugins
- **Code Intelligence** — static analysis, code indexing

### Scaling Claude
Techniques for large projects:
- **Headless mode** — `claude -p` for CI/CD and automation
- **Git Worktrees** — multiple worktrees for parallel work without conflicts
- **Agent Team** — multiple coordinated agents in parallel

### Security Best Practices
- **Claude Code Security** — minimal permissions, review before approving, never run unreviewed code

---

## Audit: What do we have?

### Legend
- ✅ Implemented
- ⚠️ Partial
- ❌ Not implemented / pending

### Basics

| Item | Status | Notes |
|------|--------|-------|
| Claude CLI installed | ✅ | Actively in use |
| Desktop App | ✅ | Claude.app available |
| Editor Extensions | ⚠️ | Not confirmed in setup |
| API usage configured | ✅ | `ANTHROPIC_AUTH_TOKEN` in env |
| CLAUDE.md project | ✅ | `CLAUDE.md` is the canonical guide |
| CLAUDE.md global (`~/.claude/`) | ✅ | `MEMORY.md` with team context |

### Core concepts

| Item | Status | Notes |
|------|--------|-------|
| Skills | ✅ | Skills in `.claude/skills/` |
| Subagents | ❌ | Not configured yet |
| MCP | ❌ | Not configured yet |
| Hooks | ✅ | `PreToolUse`: git-destructive-guard. `Stop`: statusline |
| Plugins | ❌ | Not configured |
| Context (auto-memory) | ✅ | Memory system in `~/.claude/projects/.../memory/` |
| Models configured | ✅ | Using `claude-sonnet-4-6` |

### Workflow

| Item | Status | Notes |
|------|--------|-------|
| Plan Mode | ✅ | `EnterPlanMode` available and actively used |
| Permission Modes | ✅ | `settings.json` with configurations |
| Manage Sessions (`claude -r`) | ✅ | Regular use |
| `/compact` and `/clear` | ⚠️ | Known but not always used systematically |
| Rewind | ⚠️ | Available, use not documented |

### Advanced

| Item | Status | Notes |
|------|--------|-------|
| Git Worktrees | ✅ | `EnterWorktree` available as a tool |
| Agent Team / parallelisation | ⚠️ | Subagents used ad-hoc |
| Headless mode (`claude -p`) | ⚠️ | Possible in scripts, not explicitly exploited |
| Customize Status Line | ✅ | `~/.claude/statusline.sh` — model + % context + USD cost |
| Model Configuration / Opusplan | ❌ | Always Sonnet; no Opus strategy for planning |
| Output Styles | ⚠️ | Implicit in skills (JSON via stdout), not configured globally |
| Thinking modes & Effort | ❌ | Not configured |
| Prompt Caching | ❌ | Only relevant for direct API usage |
| Security Best Practices | ✅ | CLAUDE.md has git-destructive-guard hook |

---

## Main Gaps to Address

1. **Opusplan** — use `/model` to switch to Opus in Plan Mode and Sonnet for execution
2. **Thinking modes** — explore `claude --extended-thinking` for architecture tasks
3. **Headless mode** — integrate `claude -p` into existing automation scripts
4. **Editor extensions** — confirm and document which VSCode/JetBrains extension is in use
5. **MCP servers** — configure relevant MCPs (GitHub, Google Drive, etc.)

---

## Quick References

- Full roadmap: https://roadmap.sh/claude-code
- Official docs: https://docs.anthropic.com/claude-code
- Skills: `.claude/skills/`
- Setup guide: `docs/setup/ai/claude-code-setup.md`
