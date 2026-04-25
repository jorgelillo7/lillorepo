# Claude Code — Director's Workflow

Source: Post on X by the Claude Code director (shared 2026-03)

---

## Workflow Orchestration

### 1. Plan Mode by Default

- Enter plan mode for ANY non-trivial task (more than 3 steps or architectural decisions)
- If something goes wrong, STOP and re-plan immediately; do not keep pushing
- Use plan mode for verification steps, not just for building
- Write detailed specifications upfront to reduce ambiguity

### 2. Subagent Strategy

- Use subagents frequently to keep the main context window clean
- Delegate research, exploration, and parallel analysis to subagents
- For complex problems, invest more compute via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop

- After ANY user correction: update `tasks/lessons.md` with the pattern
- Write rules for yourself to avoid the same mistake
- Iterate relentlessly on these lessons until the error rate decreases
- Review lessons at session start for the relevant project

### 4. Verification Before Finishing

- Never mark a task as completed without demonstrating it works
- Compare the diff in behaviour between the main branch and your changes when relevant
- Ask yourself: "Would a senior engineer (Staff Engineer) approve this?"
- Run tests, check logs, and prove code correctness

### 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes; do not over-engineer
- Question your own work before presenting it

### 6. Autonomous Error Correction

- When you receive a bug report: just fix it. Do not ask for hand-holding
- Identify logs, errors, or failing tests and then resolve them
- Zero context-switching needed on the user's part
- Go fix the failing CI tests without being told how

---

## Task Management

1. **Plan First**: Write the plan in `tasks/todo.md` with verifiable items
2. **Verify Plan**: Confirm before starting implementation
3. **Track Progress**: Mark items as completed as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add a review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

---

## Core Principles

- **Simplicity First**: Make each change as simple as possible. Touch the minimum necessary code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standard.
- **Minimal Impact**: Changes should only touch what is necessary. Avoid introducing bugs.
