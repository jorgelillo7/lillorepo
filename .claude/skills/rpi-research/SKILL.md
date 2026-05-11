---
name: rpi-research
description: Research mode skill that generates a structured markdown document with findings and analysis for a given topic.
model-invocable: false
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# Goal
From now on you are in research mode. The final objective is to generate a markdown file that contains all your research.

# Bootstrap

Before doing anything else, run these two scripts in this exact order:
1. Run the script at `.claude/skills/rpi-common/scripts/check-plannotator.sh` — if it fails, stop immediately and show the error to the user.
2. Run the script at `.claude/skills/rpi-common/scripts/ensure-rpi-dirs.sh`

# Information from the user
The first thing you should do is use `AskUserQuestion` to ask the user the name of the research file. Example: `<name>-research.md`. You should suggest names based on the specific research.
This is the only thing you should ask the user. Don't ask anything else.

# Rules

The research should be saved in `~/.claude/rpi/researchs/<name>-research.md`

To conduct your research you should use `Explore type subagents in parallel that use haiku as a model`. Use between 1 and 5 subagents.

To research on the internet `use the WebFetch tool, never use WebSearch,` as the organization's policies prohibit it.

Once you finish your research and have filled in the <name>-research.md with all the information obtained, use the plannotator tool by running `plannotator annotate` with the full path to the research file.

`Wait for the annotations that the user provides about the research`. It is important that you understand that this research -> human review flow is infinite in this session. Your objective should be only that. Do not try to implement or do anything else that is not this.

`Within the research it is crucial that you do not ask questions or give your opinion. Dedicate yourself only to investigating using the techniques I mentioned above.`
