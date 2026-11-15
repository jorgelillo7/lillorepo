# Subagents survive a cut

A subagent cut off by a usage limit has twice left nothing usable: no report,
work only in its context, and the next session started it again from zero.

**Every brief** for a long subagent says:
- Push after every finished step. Work that exists only in the working tree is
  lost with the agent.
- Keep a progress file in the scratchpad: one line per checklist item, with
  its status and its branch or PR. Rewrite it after every step.
- A written deliverable, such as a report, is written section by section as
  each section is done, never only at the end.

**When a usage-limit warning arrives**, tell every running subagent to stop
starting work, push what it has and send its status. Then tell the owner what
is done, what is half-done and in which branch, and what has not started.

**On resuming**, continue the same agent with SendMessage: it keeps its
context. Start a new agent only when the old one cannot be reached, and then
brief it from the progress file and the pushed branches, not from scratch.
Tell the agent to ignore any earlier "stop" message.
