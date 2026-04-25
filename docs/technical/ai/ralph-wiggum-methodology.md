# Development Methodologies

## The Ralph Wiggum Technique

**Repository:** https://github.com/ghuntley/how-to-ralph-wiggum

### What is it?

An AI-driven development methodology that uses autonomous Claude agents in loops to drastically reduce software development costs.

### Core Concept

Instead of programming manually, the system uses:
- **3 phases**: requirements definition, planning, and implementation
- **2 prompt modes**: planning (gap analysis) and building (implementation)
- **1 loop mechanism**: automated iterations with fresh context windows

The key principle: **"Context is everything"** — optimise token usage through parallel subagents and focused task execution.

### Main Components

```
project/
├── loop.sh                    # Orchestration script
├── PROMPT_plan.md            # Instructions for planning mode
├── PROMPT_build.md           # Instructions for build mode
├── IMPLEMENTATION_PLAN.md    # Prioritised task tracking
├── specs/                    # Requirements documentation
└── AGENTS.md                 # Operational guides
```

### How It Works

#### 1. Study Phase
Agents examine the specs and existing code.

#### 2. Planning Phase
Gap analysis that generates prioritised implementation tasks in `IMPLEMENTATION_PLAN.md`.

#### 3. Build Phase
Agents implement **one task per iteration**, run tests, and commit.

#### 4. Loop
Each iteration has fresh context and reads the updated plan file.

### Fundamental Principle

**"Let Ralph Ralph"** — Trust the agent to self-correct through iteration rather than micro-managing every step.

The system relies on **backpressure** (tests and validation) to maintain quality.

### Advantages

- Significantly reduces development costs
- Maintains quality through automated tests
- Leverages fresh context on each iteration
- Enables autonomous agent work
- Clear task prioritisation

### When to Use

- Projects with clear specifications
- When you have good test coverage
- For repetitive or straightforward implementation tasks
- When you want to iterate quickly with AI

### Resources

- [Original Repository](https://github.com/ghuntley/how-to-ralph-wiggum)
- Compatible with Claude Code CLI
