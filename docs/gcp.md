# GCP — services and cost decisions

Project: `biwenger-tools` · Region: `europe-southwest1` (Madrid)

## Services in use

| Service | Resource | Purpose |
|---|---|---|
| Cloud Run (Services) | `biwenger-summary` | Flask web app — comunicados, salseo, mercado, lloros awards |
| Cloud Run (Services) | `biwenger-telegram-bot` | Teams analyzer Telegram bot |
| Cloud Run (Services) | `chucknorris-bot` | Chuck Norris jokes Telegram bot |
| Cloud Run (Jobs) | `biwenger-scraper-data` | Scrapes league messages → CSV → Google Drive |
| Cloud Run (Jobs) | `biwenger-teams-analyzer` | Daily squad + market analysis → Telegram |
| Cloud Scheduler | `biwenger-scraper-trigger` | Triggers scraper job (cron) |
| Cloud Scheduler | `biwenger-teams-analyzer-trigger` | Triggers teams analyzer daily at 16:00 Madrid |
| Secret Manager | 4 secrets (see below) | Credentials and bot tokens |
| Artifact Registry | `biwenger-docker` | Docker images for all Cloud Run services/jobs |
| Cloud Logging | — | Automatic, structured logs via `get_logger()` |

## Secrets

| Secret | Contents |
|---|---|
| `biwenger-credentials-regional` | `{"email", "password", "gdrive_folder_id"}` |
| `telegram-bot-config-regional` | `{"bot_token", "chat_id", "webhook_secret"}` |
| `chucknorris-bot-config-regional` | `{"bot_token", "webhook_secret"}` |
| `biwenger-tools-sa-regional` | Google Drive service account JSON key |

All secrets are regional (`europe-southwest1`). See "Cost decisions" below.

## Cost decisions

### Regional secrets, not global
Secret Manager charges per active version (first 6 free/month). Global replication
adds a replica per region you use, counting as extra versions. Using
`--replication-policy=user-managed --locations=europe-southwest1` keeps each secret
at exactly 1 active version.

### JSON secrets — one secret, multiple values
Consolidating related credentials into a single JSON secret (e.g., `biwenger-credentials-regional`
instead of separate `biwenger-email`, `biwenger-password`, `gdrive-folder-id`) reduces
active secret count from 9 to 4, staying well within the free tier.
Config modules read the JSON first, fall back to individual env vars for local dev.

### Shared Python base image
All Cloud Run services and jobs extend a shared `python-base` image stored in Artifact Registry.
This is rebuilt only when dependencies change, not on every deploy. Benefits:
- Cold start time drops significantly (heavy deps like `google-cloud-*` are pre-installed).
- Artifact Registry storage stays low — only incremental layers change per deploy.

### min-instances = 0 on all services
No idle compute billing. All services are request-driven or job-driven.
Acceptable because this is a private league intranet, not a latency-sensitive product.

### Cloud Run instead of GCE/GKE
Serverless — no VM management, no always-on cost. Free tier: 2M requests/month,
360k vCPU-seconds, 180k GiB-seconds (shared across all services and jobs).

### europe-southwest1 (Madrid)
Chosen for latency to users (all Spanish), not for cost. Pricing is equivalent to
other European regions.

## Cost monitoring

```bash
bash scripts/check-gcp-costs.sh
```

Covers: Cloud Storage, Artifact Registry, Cloud Run services/jobs, Secret Manager,
Cloud Scheduler, Cloud Logging. Shows free-tier usage % and OK/WARN/OVER status.
For Cloud Build and Monitoring billing, check Cloud Console > Billing.
