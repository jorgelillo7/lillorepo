# RTK — Token Reduction CLI

> **Approved for internal use.** Security analysis performed (VirusTotal + Codex/Claude/Gemini). No issues found.
>
> Official repo: https://github.com/rtk-ai/rtk

`rtk` acts as a proxy between the terminal and the LLM. It filters and summarises the output of verbose commands (like Bazel) before sending it to the model, significantly reducing tokens and cost.

---

## 1. Installation

### Homebrew (recommended — macOS)

```bash
brew install rtk
```

### Quick Install (Linux / alternative macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
```

Installs to `~/.local/bin`. If it is not in your PATH, add:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## 2. Initialise the Hook (Critical Step)

After installing, register the hook that makes Claude Code automatically rewrite commands:

```bash
rtk init --global
```

This command adds the necessary hook in `~/.claude/settings.json`. Follow the on-screen instructions.

> By default it only configures **Claude Code**. For other agents:
> - `rtk init --global --opencode` — also configures OpenCode
> - `rtk init --global --gemini` — also configures Gemini CLI

**Restart Claude Code** for the hook to take effect.

### Verify the hook is working

```bash
git status
```

With the hook active, Claude Code will internally rewrite `git status` → `rtk git status` transparently. You will see no difference in the output, but the LLM will receive far fewer tokens.

---

## 3. Disable Telemetry (Recommended)

Add to your `~/.zshrc`:

```bash
export RTK_TELEMETRY_DISABLED=1
```

```bash
source ~/.zshrc
```

---

## 4. Main Subcommands

| Subcommand | Behaviour | Use case |
|------------|-----------|----------|
| `rtk test <cmd>` | Shows the last 5 lines if the command succeeds | Quick validation |
| `rtk err <cmd>` | Only shows errors (✅ if none) | Tests and builds |
| `rtk summary <cmd>` | Shows a summary of the output | Long-running executions |

---

## 5. Savings Analytics (`rtk gain`)

`rtk gain` shows how many tokens you have saved and the usage history:

```bash
rtk gain              # Accumulated savings summary
rtk gain --history    # History of commands run with individual savings
rtk discover          # Analyses Claude Code history and detects missed opportunities
```

Example output of `rtk gain`:

```
Total tokens saved: 142,831
Estimated cost savings: $0.43
Commands proxied: 87
```

---

## 6. Bazel Integration

Bazel generates very verbose output. Replace the usual commands:

| Original command | With RTK | Benefit |
|-----------------|---------|---------|
| `bazel test //...` | `rtk err bazel test //...` | Only shows failures |
| `bazel build //...` | `rtk err bazel build //...` | Only shows compilation errors |
| `bazel run //...` | `rtk summary bazel run //...` | Execution summary |

### Example — Tests with no failures

```bash
$ rtk err bazel test //pkg/mas-stack/bss/mas-documents/core/scoring/...

✅ Command completed successfully (no errors)
```

### Example — Tests with failures

```bash
$ rtk err bazel test //pkg/mas-stack/bss/mas-documents/core/scoring/... 2>&1

FAILED: //pkg/mas-stack/bss/.../ExpireScoringServiceTest
org.opentest4j.AssertionFailedError: expected: <999> but was: <1>
    at ...ExpireScoringServiceTest.should_expire_scoring_successfully(ExpireScoringServiceTest.java:57)
```

The full log is saved in `~/Library/Application Support/rtk/tee/` so the LLM can consult it if it needs more context.

---

## 7. AI Agent Configuration (Claude Code / Opencode)

For agents to use `rtk` automatically with Bazel, configure aliases in your `~/.zshrc`:

```bash
# RTK Bazel aliases
alias btest='rtk err bazel test'
alias bbuild='rtk err bazel build'
alias brun='rtk summary bazel run'
```

If you use **Opencode**, add the rewrites directly in its configuration:

```typescript
const BAZEL_REWRITES: Record<string, string> = {
  "bazel test": "rtk err bazel test",
  "bazel build": "rtk err bazel build",
  "bazel run": "rtk summary bazel run",
};
```

---

## 8. Verify Installation

```bash
rtk --version   # Should show "rtk 0.x.x"
rtk gain        # Should show statistics (not "command not found")
```

---

## Resources

- **Official repo:** https://github.com/rtk-ai/rtk
