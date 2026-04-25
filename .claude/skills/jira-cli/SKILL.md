---
name: jira-cli
description: "ALWAYS use this skill for ANY Jira-related request. Triggers on: creating issues/tickets/tasks/epics, viewing or updating Jira items, searching with JQL, managing sprints, navigating Initiative > Epic > Task hierarchies, linking issues, transitioning statuses, any mention of Jira, SWE-XXX issue keys, or Jira workflows."
---

# Jira CLI

Wrapper around the `jira` CLI (ankitpokhrel/jira-cli) for Jira Server at https://jiranext.masorange.es.

## Pre-flight

Verify setup before any operation:

```bash
jira version  # CLI installed
jira me       # authentication active
```

If either fails, see [references/authentication.md](references/authentication.md).

## Rules

1. **Epics** — always use `jira epic create`, never `jira issue create -t Epic`. Epics require the `-n` flag for Epic Name.
2. **Link syntax** — `jira issue link SOURCE TARGET TYPE`. SOURCE has the relationship WITH TARGET. Order matters.
3. **Multi-project search** — append `AND project is not EMPTY` to JQL when searching across all projects.
4. **Valid link types**: `Blocks`, `Duplicate`, `Include`, `Relates`, `Problem/Incident`.
5. **Issue hierarchy** — Tasks link to Epics via `-P` flag at creation; Epics link to Initiatives via `jira issue link`. See [references/hierarchy.md](references/hierarchy.md).

## References

- **[commands.md](references/commands.md)** — Full CLI command reference by category (issues, epics, sprints, metadata)
- **[hierarchy.md](references/hierarchy.md)** — Initiative → Epic → Task hierarchy with complete creation and linking flows
- **[authentication.md](references/authentication.md)** — Initial setup, config YAML, Personal Access Token
- **[error-handling.md](references/error-handling.md)** — Common errors, causes, and resolutions
