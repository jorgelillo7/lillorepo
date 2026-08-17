# Long-Running Agent Sessions

Keeping a Claude Code session alive while it works: surviving a dropped
connection, a closed window, and the Mac going to sleep.

These are three different failures with three different fixes. Solving one and
assuming you are covered is the usual mistake — a terminal multiplexer does
nothing about sleep, and a sleep blocker does nothing about a closed window.

| Failure | What dies | Fix |
|---|---|---|
| Wi-Fi drops, SSH cuts, window closed | The process and everything under it | `byobu` |
| Mac goes to sleep | Nothing dies, but work pauses | `caffeinate` |
| Laptop lid closed | Sleeps regardless | Nothing — see the caveat below |

---

## Session persistence: byobu

`byobu` is a friendly layer over `tmux`. It runs a terminal server in the
background, so the processes inside it keep running whether or not any window
is attached to them.

```bash
brew install byobu    # pulls tmux in as a dependency
```

### The rule that matters

**Run `byobu` on the machine doing the work**, not on the one you are typing
from.

- **Remote (SSH):** `ssh server` → `byobu` → `claude`. If the network drops,
  reconnect and type `byobu` — you are back in the same session, with the
  agent having carried on the whole time.
- **Local:** `byobu` → `claude`. Protects against closing the window by
  accident, which is the way most local sessions actually die.

Running `byobu` locally and then SSH-ing out of it protects nothing: the work
is happening on the far end, and that is where the session needs to survive.

### Why this matters inside VS Code's terminal

An agent started in VS Code's integrated terminal is a **child of VS Code**:

```
zsh → claude → zsh → Code Helper → Code
```

Quit VS Code — or upgrade it, which quits it — and the whole branch dies. It
happened here: a `brew upgrade --cask visual-studio-code` killed the session
running the upgrade, returning exit code 137 mid-command.

`byobu` breaks that chain. tmux starts a **server detached from the terminal
that launched it**, so the processes inside belong to the server rather than
to VS Code. The editor can quit, crash or update, and reopening a terminal and
typing `byobu` returns you to a session that never stopped.

The narrower rule, which costs nothing: **never upgrade the app you are
running inside.** Do it from a different terminal, or from within byobu.

### The recipe, for the usual VS Code flow

Open the repo in VS Code as always, then in the integrated terminal:

```bash
byobu new -A -s claude     # attach if it exists, create if it does not
claude                     # then /rc, or whatever you normally do
```

`-A` is what makes it a single command worth memorising: the same line starts
the session the first time and reattaches every time after, so there is no
"did I already have one open?" branch to think about.

When VS Code dies — crash, accidental quit, or an upgrade — reopen it, open a
terminal, and run the exact same line. You land back in the session that never
stopped.

An alias is worth it. Pick your own name — just check it is free first, since
the obvious short ones are taken (`cc` is the C compiler, `bc` the
calculator):

```bash
type <name> || echo free
echo "alias <name>='byobu new -A -s claude'" >> ~/.zshrc
```

**Detaching:** `F6`, or `Ctrl-a d` if the function keys are captured. VS Code
and Claude Code both bind function keys, so `F2`–`F6` may not reach byobu from
the integrated terminal. That only costs you byobu's tab management — the
persistence, which is the whole point, does not depend on any keybinding. If
the shortcuts get in the way rather than help:

```bash
byobu-keybindings          # toggles byobu's F-key bindings off
```

### The shortcuts you will actually use

| Key | Does |
|---|---|
| `byobu` | Start a session, or reattach to the one already running |
| `F2` | New tab |
| `F3` / `F4` | Previous / next tab |
| `F6` | Detach — leave it running and get your prompt back |
| `exit` | Close the current tab (closing the last one ends the session) |

`F6` is the one worth remembering: detaching deliberately is how you leave a
long agent run going and reclaim your terminal.

> **Careful with `exit`.** It closes the tab for good. Detaching is `F6`.

---

## Sleep prevention: caffeinate

`byobu` keeps the process alive across a disconnect, but a sleeping Mac still
pauses the work. macOS ships `caffeinate` — nothing to install.

```bash
caffeinate -i byobu     # the combination worth memorising
```

`-i` prevents idle sleep. The important property is that **`caffeinate` binds
to the command it launches**: while that command runs the Mac stays awake, and
the moment it exits the machine goes back to its normal power behaviour. No
toggle to remember, no battery quietly draining for the next three days
because you forgot to turn something off.

| Flag | Prevents |
|---|---|
| `-i` | Idle system sleep — the one you want |
| `-d` | Display sleep (screen stays lit; rarely what you want) |
| `-m` | Disk sleep |
| `-s` | System sleep, on AC power only |

### The caveat nobody mentions until it bites

**Closing the lid sleeps a MacBook regardless of `caffeinate`.** No flag
overrides it. The only way to run with the lid shut is clamshell mode:
connected to power *and* an external display (or, on modern macOS, at least
power plus an external input/display setup).

If you are walking away from a long run, leave the lid open.

### GUI alternatives

`caffeinate` covers the case fully. If you would rather click than type:

- **Amphetamine** (App Store, free) — the capable one. Its "Triggers" can keep
  the Mac awake automatically whenever your terminal app is running, so you
  never have to remember at all.
- **KeepingYouAwake** (`brew install --cask keepingyouawake`) — a menu-bar
  toggle, one click on and off.

> **Do not install `caffeine`.** It is unmaintained and predates Apple
> Silicon. `mac-setup.md` recommended it until this page replaced that advice;
> if you already have it:
> ```bash
> brew uninstall --cask caffeine
> ```

---

## What this does *not* protect

Worth being explicit, because it changes how much any of this matters:

- **Deploys do not run on your Mac.** `deploy.yml` runs on GitHub Actions, so a
  merged PR ships whether your laptop is awake, asleep, or shut. Losing a local
  session loses the session, never a deploy.
- **Background tasks belong to the session.** Anything Claude Code started in
  the background dies with the session it was started from, which is exactly
  what `byobu` is for.
- **A dead session is not a lost repo.** Committed work is safe; uncommitted
  edits in the working tree survive too. What is lost is the agent's context —
  which is the expensive part, and the reason this page exists.

---

## The whole thing

```bash
caffeinate -i byobu     # then run claude inside it
```

One command. Survives a closed window, a dropped connection and an idle
timeout. Press `F6` to walk away, type `byobu` to come back.
