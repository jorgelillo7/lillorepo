# Jira CLI — Authentication

## Config Location

`~/.config/.jira/.config.yml`

```yaml
auth_type: bearer
server: https://jiranext.masorange.es
login: user@masorange.es
project:
  key: SWE
```

## Initial Setup

Run `jira init` and configure:
- **Installation type**: `Local`
- **Authentication type**: `bearer`

## Personal Access Token (PAT)

1. Go to your Jira profile
2. Click **Personal Access Tokens** in the left sidebar
3. Click **Create token**, give it a name (e.g., `My_jira_cli`) and set expiry
4. Copy the generated token immediately (shown only once)
5. Export the environment variable:

```bash
export JIRA_API_TOKEN=<your-personal-access-token>
```

Add to `~/.zshrc` or `~/.bashrc` to persist across sessions.

6. Run `jira init`, select `bearer` auth type and paste your PAT when prompted.

## Verify

```bash
jira version  # CLI installed
jira me       # authentication active
```
