# Jira CLI — Command Reference

## Issues

| Operation | Command | Example |
|-----------|---------|---------|
| **View** | `jira issue view <KEY>` | `jira issue view SWE-705 --plain` |
| **List** | `jira issue list -p PROJECT` | `jira issue list -p SWE -s "In Progress"` |
| **Search (single project)** | `jira issue list -q "JQL"` | `jira issue list -q "project = SWE AND assignee = currentUser()"` |
| **Search (all projects)** | `jira issue list -q "JQL AND project is not EMPTY"` | `jira issue list -q "assignee = currentUser() AND statusCategory != Done AND project is not EMPTY"` |
| **Create Task** | `jira issue create` | `jira issue create -p SWE -t Task -P SWE-705 -s "Title" --no-input` |
| **Edit** | `jira issue edit <KEY>` | `jira issue edit SWE-1234 -s "New title"` |
| **Transition** | `jira issue move <KEY>` | `jira issue move SWE-1234 "Done" -R "Fixed"` |
| **Link** | `jira issue link SOURCE TARGET TYPE` | `jira issue link SWE-457 SWE-705 "Include"` |
| **Open in browser** | `jira open <KEY>` | `jira open SWE-705` |

### Create Task — Full Options

```bash
jira issue create -p SWE -t Task -P SWE-705 --no-input \
  -s "Implement OAuth2 token refresh" \
  -b "Add automatic token refresh before expiration" \
  -y High \
  -l backend -l security \
  -a "juan.palacios@masmovil.com"
```

**Issue types**: Initiative, Epic, Task, Incidence
**Priority values**: Highest, High, Medium, Low, Lowest

## Epics

```bash
jira epic create -p SWE -n "Device Insurance Migration" --no-input \
  -s "Migrate Device Insurance Orchestrator to Temporal" \
  -b "Remove Spring Boot dependencies and use pure Temporal SDK" \
  -y High
```

List tasks in an epic:
```bash
jira epic list SWE-705 -p SWE
```

## Sprints

| Operation | Command |
|-----------|---------|
| **List boards** | `jira board list` |
| **List sprints** | `jira sprint list -b BOARD_ID [--state active]` |
| **Add to sprint** | `jira sprint add SPRINT_ID ISSUE-1 ISSUE-2` |

## Metadata

| Operation | Command |
|-----------|---------|
| **List projects** | `jira project list` |
| **Current user** | `jira me` |
