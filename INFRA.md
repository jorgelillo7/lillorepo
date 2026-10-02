# INFRA — GCP inventory at a glance

One screen to know **which projects exist, which services each one uses, and
where they live**. The *why* behind every choice stays in `docs/gcp.md`
(cost decisions, single-region policy, secret consolidation). Update this
file whenever a service/bucket/secret is added or moved — `scripts/check-gcp-costs.sh`
audits most of what's listed here. The static layer of both projects (accounts,
grants, secrets, registries, buckets, Firestore settings, Scheduler, budgets) is
declared as code in [`infra/`](infra/README.md); this file is the readable
summary, `infra/` is what a `terraform plan` checks.

Default region: **`europe-southwest1` (Madrid)** — deviations are called out.

---

## Project `biwenger-tools`

The Biwenger league platform (packages `biwenger_tools` + `chucknorris_bot`).

| Product | In use | Notes |
|---|---|---|
| Cloud Run (services) | `biwenger-api` · `biwenger-bot` · `biwenger-summary` (web) · `chucknorris-bot` | All minScale=0 |
| Cloud Run (jobs) | `biwenger-scraper-data` | Sundays 22:00 via Scheduler |
| Firestore | `(default)` — `europe-southwest1` | comunicados, clausulazos, participacion, tabla_justicia, palmares, auto_bid_log |
| Cloud Storage | `biwenger` — **`us-central1`** | public read; the newspaper, the draft market CSV and the cup-winner images. Written by `run-biwenger-api`; one league member may upload under `special-tournaments/` only. US for the always-free tier, as `be-water-photos` |
| Cloud Storage | `lillorepo-tfstate` — **`us-central1`** | private, versioned Terraform state for both projects ([`infra/`](infra/README.md)); created by hand, not by Terraform |
| Artifact Registry | `biwenger-docker` | service images + shared `python-base` (linux/amd64 only, bytecode compiled in) |
| Secret Manager | 2 secrets ×1 active version | `biwenger-secrets`, `chucknorris-secrets` — one regional JSON secret per package; no key files |
| Cloud Scheduler | 2 jobs — **`europe-west1`** | daily digest 09:00 + weekly scraper (Scheduler is not offered in Madrid) |
| Workload Identity Federation | pool `github` / provider `github-oidc` | keyless deploys for the whole repo, restricted to `jorgelillo7/lillorepo` **on `master`** |
| Workload Identity Federation | pool `github-plan` / provider `github-plan` | read-only `terraform plan` from `infra.yml` on any ref, as `terraform-plan` |
| Service accounts | `run-biwenger-api` · `-bot` · `-web` · `-scraper` · `run-chucknorris-bot` · `scheduler-invoker` · `biwenger-tools-sa` (CI) · `terraform-plan` (CI, read-only) | one per service, minimal grants — what each may do: `README.md` → "Service accounts"; the default compute account holds **no role** |
| Budget | €1/month alert — **billing-account wide** | not filtered to this project: it watches everything on the account |

## Project `be-water-app`

The Be Water catalog (package `be_water`).

| Product | In use | Notes |
|---|---|---|
| Cloud Run (services) | `be-water` | minScale=0, public |
| Firestore | `(default)` — `europe-southwest1` | waters, users, water_revisions (created on the first composition overwrite) |
| Cloud Storage | `be-water-photos` — **`us-central1`** | bottle photos, public read. Deliberately US: Storage's 5 GB always-free tier only exists in US regions; Madrid would bill from byte one |
| Artifact Registry | `be-water-docker` | `web` image (base pulled from `biwenger-docker`) |
| Secret Manager | 1 secret ×1 version | `be-water-secrets` (JSON: flask key + Telegram bot + Gemini key — consolidated on purpose) |
| Service account | `run-be-water` | Firestore, objects in `be-water-photos`, `be-water-secrets` — the compute default holds no role |
| Budget | €1/month alert | filtered to this project |

Deploys to this project run from the shared WIF service account
(`biwenger-tools-sa`), granted `run.admin` + `artifactregistry.writer` +
actAs on `run-be-water`, plus `artifactregistry.repoAdmin` on the `be-water-docker`
repo so the CI cleanup job can delete old digests.

## Outside GCP (but part of the picture)

| Thing | Where | Notes |
|---|---|---|
| Gemini API keys | free: `gen-lang-client-0434934257` · paid fallback: `gen-lang-client-0059905191` ("Be Water") | paid project: billing linked + €1 budget + a **daily cap** of 200 text / 50 image requests (`packages/be_water/OPERATIONS.md`) |
| Telegram bots | `@be_water_app_bot` (catalog notifications) · biwenger league bot · Chuck Norris bot | tokens in Secret Manager |
| GitHub secrets | 2 | `COMPETICIONES_SHEET_IDS_25_26`, `COMPETICIONES_SHEET_IDS_26_27` — one per season, `;`-separated ids (+ WIF needs none) |

## Cost guardrails

- Cloud Scheduler uses **2 of 3** free jobs across the billing account (the
  quota is per billing account, not per project — one more cron is free, the
  one after that needs a paid job or a consolidation), and photo storage rides
  the US always-free tier.
- **Secret Manager sits at 3/6** (one JSON secret per package). The free tier is 6 *active*
  versions per billing account, and "active" counts **Enabled and Disabled
  alike** — disabling a version does not stop it billing, only destroying it
  does. The account reached 8 once, because rotating a secret adds a version
  and the repo-wide runbook never said to destroy the one it replaced; see
  "Updating a secret" in `docs/operations.md`, which now does. Overage is
  $0.06 per version per month. Nothing prunes automatically —
  `scripts/check-gcp-costs.sh` reports, it does not clean. A new package
  should keep to one JSON secret, as the three existing ones do.
- **Artifact Registry's 0.5 GB is per billing account too.** Steady state is
  well under it (a 127 MB amd64 base shared by every service image, plus each
  package's thin layers); a base rebuild adds a full copy until the CI cleanup
  removes untagged digests older than 24 h, so rebuild once per change, not
  per experiment, and move `latest` only after the merge
  (`.claude/skills/check-deps/UPGRADING.md`).
- Three €1 monthly budget alerts on the billing account: one account-wide,
  one on `be-water-app`, one on the paid Gemini project.
  `scripts/check-gcp-costs.sh` is the auditor — run without flags it sweeps
  both projects and closes with the account-wide Secret Manager version count.
