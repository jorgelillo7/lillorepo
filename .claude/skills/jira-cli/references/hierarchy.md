# Jira CLI — Issue Hierarchy

## Structure

```
Initiative SWE-457 (Monorepo Temporal POC)
├── Epic SWE-705 (Device Insurance Migration)
│   ├── Task SWE-706 (Create Manual Configuration System)
│   ├── Task SWE-707 (Configure Temporal Worker Manually)
│   └── Task SWE-708 (Implement Manual DI for Activities)
└── Epic SWE-465 (MasOrange temporal library)

Incidence SWE-100              # Standalone - not linked to hierarchy
```

## Linking Rules

- **Task → Epic**: use `-P SWE-705` flag when creating the task
- **Epic → Initiative**: use `jira issue link SWE-457 SWE-705 "Include"` after creating the epic

## Complete Flow: Epic with Tasks under Initiative

```bash
# 1. Create Epic
jira epic create -p SWE -n "Auth Migration" -s "Migrate to OAuth2" --no-input
# Returns: SWE-XXX

# 2. Link Epic to Initiative (Initiative includes Epic)
jira issue link SWE-457 SWE-XXX "Include"

# 3. Create Tasks under Epic
jira issue create -p SWE -t Task -P SWE-XXX -s "Task 1" --no-input
jira issue create -p SWE -t Task -P SWE-XXX -s "Task 2" --no-input
jira issue create -p SWE -t Task -P SWE-XXX -s "Task 3" --no-input
```

## JQL to Navigate Hierarchy

```bash
# Tasks under a specific epic
jira issue list -q "\"Epic Link\" = SWE-705"

# Epics under an initiative
jira issue list -q "issueType = Epic AND issue in linkedIssues(SWE-457, \"is included by\")"

# All open tasks across all projects
jira issue list -q "assignee = currentUser() AND statusCategory != Done AND project is not EMPTY"
```

## Project Keys Reference

Domain-to-project key mapping: `tools/swe-jira-initiatives-manager/config.csv`

Format: `domain-name,PROJECT_KEY` (e.g., `mas-billing,MBIL`)

Run `jira project list` for the complete list.
