# Jira CLI — Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `Project not found` | Invalid project key | Run `jira project list` to verify available keys |
| `Invalid transition` | Status not available from current state | Run `jira issue view KEY` to see current status and valid transitions |
| `User not found` | Invalid assignee format | Use exact email address or display name |
| `invalid issue link type` | Wrong link type string | Valid types: `Blocks`, `Duplicate`, `Include`, `Relates`, `Problem/Incident` |
| `Issue does not exist` | Invalid issue key | Verify key format (`PROJECT-NUMBER`) and that the issue exists |
| `jira: command not found` | CLI not installed | Install from github.com/ankitpokhrel/jira-cli |
| Authentication errors | Token expired or missing | See [authentication.md](authentication.md) for PAT setup |
