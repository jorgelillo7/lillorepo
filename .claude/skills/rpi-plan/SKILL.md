---
name: rpi-plan
description: Planning mode skill that generates a structured markdown implementation plan for a given task.
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
From now on you are in plan mode. The final objective is to generate a markdown file that contains the full implementation plan.

# Bootstrap

Before doing anything else, run these two scripts in this exact order:
1. Run the script at `.claude/skills/rpi-common/scripts/check-plannotator.sh` — if it fails, stop immediately and show the error to the user.
2. Run the script at `.claude/skills/rpi-common/scripts/ensure-rpi-dirs.sh`

# Information from the user
The first thing you should do is use `AskUserQuestion` to ask the user if there is an existing research to base this plan on. List the most recent files in `~/.claude/rpi/researchs/` as candidates. Also give the option to plan without a prior research.

- If the user picks an existing research: derive the plan name directly from the research filename (e.g. `foo-research.md` → `foo-plan.md`). Do not ask the user anything else.
- If the user chooses no prior research: use a second `AskUserQuestion` to ask for the plan file name (suggest names based on the specific plan). Do not ask anything else.

# Rules

The plan should be saved in `~/.claude/rpi/plans/<name>-plan.md`

The plan must be extensive and detailed. It must include code snippets showing the exact changes intended to be made — new functions, modified signatures, updated logic, etc. These snippets are not illustrative; they must reflect the actual code that would need to be written or changed. It is very important to show the before vs after.

If a prior research file was provided, read it before starting to plan. The research is your primary source — base the plan on it. You may still use subagents to clarify specific things that were not fully covered in the research, but the research drives the plan.

If no prior research was provided, use `Explore type subagents in parallel that use haiku as a model` (between 1 and 5 subagents) to gather the necessary information before planning.

Once you finish your plan and have filled in the <name>-plan.md with all the information obtained, use the plannotator tool by running `plannotator annotate` with the full path to the plan file.

`Wait for the annotations that the user provides about the plan`. It is important that you understand that this plan -> human review flow is infinite in this session. Your objective should be only that. Do not try to implement or do anything else that is not this.
