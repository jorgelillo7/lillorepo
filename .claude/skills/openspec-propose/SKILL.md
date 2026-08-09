---
name: openspec-propose
description: Spec-first authoring for a feature that does not exist yet — interviews the user for the behaviour, drafts openspec/changes/{name}/ (proposal, design, tasks, spec deltas), and folds the deltas into openspec/specs/ once the code and its tests land. Use before writing the feature, not after. Hands the implementation plan to rpi-plan.
model-invocable: false
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# Goal

Agree on **what** a not-yet-existing feature must do, in writing, before anyone
writes it. The output is `openspec/changes/{name}/`; the endpoint, much later,
is a requirement folded into `openspec/specs/` with real tests behind it.

The `how` is not yours. See § "Handoff to rpi-plan" — duplicating the
implementation plan here is the failure mode this skill exists to avoid.

# Step 0 — Read before you ask

Read `CLAUDE.md` § "Specs", `openspec/project.md`, `openspec/changes/README.md`,
and the spec of the capability this feature touches (or its neighbours, if it
is a new capability).

**Never ask the user something the repo answers.** Which package it belongs
to, what the existing capability is called, the test framework and naming
convention, the deploy target, the layer rules — all of that is on disk, and
asking wastes the one resource the interview has: the user's patience for the
questions only they can answer.

# Step 1 — Interview

`AskUserQuestion`, in as few rounds as the ambiguity allows. Ask about:

1. **The observable behaviour.** What is true after the feature exists that is
   not true now, stated so a non-programmer could check it. If the answer is
   phrased as a mechanism ("add a field to the payload"), push once for the
   outcome it buys.
2. **The trigger and the actor.** Who or what sets it off, and how often.
3. **The edge cases.** Empty input, upstream down, the value at the boundary
   of a threshold, the second concurrent run. Name the ones you can see in the
   surrounding code and ask which are real; do not ask an open "any edge
   cases?", which reliably returns "no".
4. **What must NOT happen.** The negative requirement is the one that gets lost
   and the one the incident is later about — does it fall back silently, retry,
   or fail loud? Does it ever write, notify, or spend?
5. **The reason.** What went wrong, or what is impossible today. This becomes
   the motive paragraph, and a requirement without one gets deleted by a future
   reader who cannot see the point of it.

Stop asking when you could write the SHALL sentences without guessing.

# Step 2 — Draft `openspec/changes/{name}/`

Kebab-case `{name}`. Layout per `openspec/changes/README.md`:

```
openspec/changes/{name}/
├── proposal.md   # why, and what changes, at a glance
├── design.md     # the approach and the trade-offs the behaviour depends on
├── tasks.md      # checklist of outcomes, including the test names below
└── specs/{package}/{capability}/spec.md   # the delta
```

The delta file holds only what changes, each block labelled:

```markdown
## ADDED Requirements

### Requirement: <claim>
<motive paragraph>

#### Scenario: <case>
- **WHEN** … - **THEN** …
- *Verifies:* `test_intended_name`

## MODIFIED Requirements
### Requirement: <existing title, verbatim — that is how it is matched>
<the new text in full, not a diff>

## REMOVED Requirements
### Requirement: <existing title>
<why it no longer holds>
```

Same house style as a real spec: SHALL wording, a motive that states the
constraint or the incident, no dates and no commit hashes.

# Step 3 — Approval

Show the user the proposal and the delta and get an explicit yes. The whole
value of spec-first is that disagreement surfaces here, where it costs a
paragraph instead of a branch.

Only after approval does implementation begin — via `rpi-plan`, not here.

# Naming tests that do not exist yet

This is the sharpest edge in the flow. A proposal writes scenarios **before**
the tests, so it names tests that are not there.

- **The delta is safe where it sits.** `scripts/check_specs.py` only scans
  `openspec/specs/`; nothing under `openspec/changes/` is checked. That is
  precisely why the delta stays in `changes/` until the code lands.
- **The intended names are a contract.** Copy every `*Verifies:*` name into
  `tasks.md` as its own checklist line. The implementation must create
  functions with **exactly** those names.
- **Match the repo's test-naming convention** — a sentence about what must
  hold (`test_a_promoted_substitute_never_gets_the_armband`), not
  `test_function_name_case_3`. Read the neighbouring test file first; a name
  invented in a spec that reads nothing like its neighbours is the one that
  gets "tidied up" during review.
- **If the implementer renames a test**, one of the two is wrong and both are
  cheap to fix: rename back, or update the scenario in the same PR. What is not
  allowed is landing the rename and leaving the spec pointing at a ghost —
  `check_specs.py` fails, and the failure lands on whoever pushes next.

# Step 4 — Archive, when the code has landed

Gate: the feature is merged **and** the named tests exist and pass. Not before
— folding a delta into `specs/` early breaks `check_specs.py` for everyone.

1. Fold each delta block into `openspec/specs/{package}/{capability}/spec.md`
   (ADDED appended, MODIFIED replacing the block with the matching title,
   REMOVED deleted).
2. Register the capability in `openspec/project.md`'s table if it is new.
3. Delete `openspec/changes/{name}/`. `openspec/changes/` is empty between
   changes — that emptiness is the signal that nothing is half-landed. Keep the
   history under `openspec/archive/{date}-{name}/` only if the user asks for
   it; the default is delete, since `git log` already has it.
4. ```bash
   python3 scripts/check_specs.py
   ```
   It must pass. If it does not, the tests are not named what the spec claims —
   fix that now, while it is one file.

# Handoff to rpi-plan

**This skill states the WHAT. `rpi-plan` states the HOW.**

`design.md` may record the approach and the trade-offs the *behaviour* depends
on: which data source is authoritative, where the boundary sits, what is
deliberately not handled, what the alternatives cost. That is context a reader
needs to judge whether the requirement is right.

The handoff point is concrete: **the moment you would write a function
signature, a code snippet, or a file-by-file change list, stop.** That is
`rpi-plan`'s output, and it wants an annotated review loop this skill does not
have. `tasks.md` here is a checklist of outcomes and test names, not a plan.

After Step 3's approval, say so explicitly and invoke `rpi-plan`, giving it the
approved proposal as its input. A plan written against an approved spec is the
best case that workflow gets.

# Rules

- Never ask what the repo can tell you; always ask what only the user knows.
- One change folder at a time. Two in flight means neither is landing.
- No implementation code in `openspec/` — not even illustrative snippets.
- Do not fold a delta into `specs/` before the tests exist.
- Leave `openspec/changes/` empty when the change is done.
