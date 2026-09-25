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

Gather the research with Explore subagents, run in parallel when the questions are independent of each other.

Once you finish your research and have filled in the <name>-research.md with all the information obtained, use the plannotator tool by running `plannotator annotate` with the full path to the research file.

Then wait for the user's annotations and revise the file against them. The session stays in this research → review loop until the user ends it; implementing anything is out of scope.

The research file records findings, not recommendations or open questions: the plan stage is where choices get made.
