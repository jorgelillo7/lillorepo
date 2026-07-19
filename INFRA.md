# INFRA — GCP inventory at a glance

One screen to know **which projects exist, which services each one uses, and
where they live**. The *why* behind every choice stays in `docs/gcp.md`
(cost decisions, single-region policy, secret consolidation). Update this
file whenever a service/bucket/secret is added or moved — `scripts/check-gcp-costs.sh`
audits most of what's listed here.

Default region: **`europe-southwest1` (Madrid)** — deviations are called out.

---

## Project `biwenger-tools`

The Biwenger league platform (packages `biwenger_tools` + `chucknorris_bot`).

| Product | In use | Notes |
|---|---|---|
| Cloud Run (services) | `biwenger-api` · `biwenger-bot` · `biwenger-summary` (web) · `chucknorris-bot` | All minScale=0 |
| Cloud Run (jobs) | `biwenger-scraper-data` | Sundays 22:00 via Scheduler |
| Firestore | `(default)` — `europe-southwest1` | comunicados, clausulazos, participacion, tabla_justicia, palmares, auto_bid_log |
| Artifact Registry | `biwenger-docker` | service images + shared `python-base` |
| Secret Manager | 5 secrets ×1 version | biwenger-credentials, tools-sa, telegram-bot-config, chucknorris-bot-config, flask-web-config (all `-regional`) |
| Cloud Scheduler | 2 jobs — **`europe-west1`** | daily digest 09:00 + weekly scraper (Scheduler is not offered in Madrid) |
| Workload Identity Federation | pool `github` / provider `github-oidc` | keyless deploys for the whole repo, restricted to `jorgelillo7/lillorepo` |
| Budget | €1/month alert | |

## Project `be-water-app`

The Be Water catalog (package `be_water`).

| Product | In use | Notes |
|---|---|---|
| Cloud Run (services) | `be-water` | minScale=0, public |
| Cloud Run (jobs) | `be-water-catalog-sync` | monthly via Scheduler; reuses the `web` image with a command override (extracts `core_srcs.tar`, runs `catalog_sync`) — CI refreshes its image on every be_water deploy |
| Cloud Scheduler | `be-water-catalog-sync-monthly` — **`europe-west1`** | day 1, 09:00 Madrid |
| Firestore | `(default)` — `europe-southwest1` | waters, users |
| Cloud Storage | `be-water-photos` — **`us-central1`** | bottle photos, public read. Deliberately US: Storage's 5 GB always-free tier only exists in US regions; Madrid would bill from byte one |
| Artifact Registry | `be-water-docker` | `web` image (base pulled from `biwenger-docker`) |
| Secret Manager | 1 secret ×1 version | `flask-web-config-regional` (JSON: flask key + Telegram bot + Gemini key — consolidated on purpose) |
| Budget | €1/month alert | |

Deploys to this project run from the shared WIF service account
(`biwenger-tools-sa`), granted `run.admin` + `artifactregistry.writer` +
actAs here, plus `artifactregistry.repoAdmin` on the `be-water-docker`
repo so the CI cleanup job can delete old digests.

## Outside GCP (but part of the picture)

| Thing | Where | Notes |
|---|---|---|
| Gemini API key | AI Studio project `gen-lang-client-0059905191` ("Be Water") | billing linked + €1 budget; image gen needs prepaid AI-credit top-ups (bought in AI Studio) — text/OCR rides the free tier |
| Telegram bots | `@be_water_app_bot` (catalog notifications) · biwenger league bot · Chuck Norris bot | tokens in Secret Manager |
| GitHub secrets | 3 | `LIGAS_ESPECIALES_SHEET_ID_25_26`, `TROFEOS_SHEET_ID_25_26` (+ WIF needs none) |

## Cost guardrails

- Everything above fits the free tiers **except** sub-cent dust: Secret
  Manager sits at exactly **6/6 free versions across the billing account**
  (quota is per billing account, not per project — consolidate before
  creating a 7th), Cloud Scheduler at **3/3 free jobs** (same account-wide
  quota — the next cron needs a paid job or a consolidation), and photo
  storage rides the US always-free tier.
- One €1 budget alert per project; `scripts/check-gcp-costs.sh` is the
  auditor — run without flags it sweeps both projects and closes with the
  account-wide Secret Manager version count.
