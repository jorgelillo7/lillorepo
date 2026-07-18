# CI/CD — deploy.yml

Workflow that runs on every push to `master` when files under `core/`, `packages/`, `tools/`, `docker/`, `MODULE.bazel` or `.github/workflows/` change.

## Stages

```
Lint → Detect changed modules → Run tests ─┬→ Deploy web ────────────┐
                                            ├→ Deploy scraper ────────┤
                                            ├→ Deploy api ────────────┼→ Clean up old images
                                            ├→ Deploy bot ────────────┤
                                            ├→ Deploy chucknorris_bot ┤
                                            └→ Deploy be_water ───────┘
```

1. **Lint** — flake8 + `black --check`.
2. **Detect changed modules** — `paths-filter` per service decides which deploys to run. `core/`, `tools/`, `docker/` or `MODULE.bazel` triggers all of them; a package-only change only its own deploy.
3. **Run tests** — full Bazel test sweep for all packages.
4. **Deploy (parallel)** — each service builds and pushes its OCI image, then deploys/updates the matching Cloud Run resource:
   - **web** → `biwenger-summary` Cloud Run Service
   - **scraper_job** → `biwenger-scraper-data` Cloud Run Job
   - **api** → `biwenger-api` Cloud Run Service (`--no-allow-unauthenticated`)
   - **bot** → `biwenger-bot` Cloud Run Service
   - **chucknorris_bot** → `chucknorris-bot` Cloud Run Service
   - **be_water/web** → `be-water` Cloud Run Service on the `be-water-app` project (cross-project, see below)
5. **Clean up old images** — runs `scripts/clean-images-artifact.sh` to prune stale digests from both Artifact Registry repos (`biwenger-docker` + `be-water-docker`).

## Required GitHub secrets

| Secret | Description |
|--------|-------------|
| `LIGAS_ESPECIALES_SHEET_ID_25_26` | Google Sheets ID (ligas especiales 25-26) |
| `TROFEOS_SHEET_ID_25_26` | Google Sheets ID (trofeos 25-26) |

Other credentials (Biwenger login, Telegram bot tokens, JP token, Flask
`secret_key`/`admin_password` via `flask-web-config-regional`) live in Secret
Manager and are injected at runtime via `--update-secrets`, not as GitHub secrets.

GCP auth is keyless: the workflow exchanges its GitHub OIDC token for
short-lived `biwenger-tools-sa` credentials via Workload Identity Federation
(pool `github`, provider `github-oidc`, restricted to this repository). There
is no service-account key to rotate or leak.

## Service account permissions

Service account: `biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com`

### Project-level roles

| Role | Why |
|------|-----|
| `roles/viewer` | Read project metadata |
| `roles/artifactregistry.writer` | Push Docker images to Artifact Registry |
| `roles/run.developer` | Deploy and update Cloud Run services and jobs |

### Resource-level bindings

| Resource | Role | Why |
|----------|------|-----|
| `319945089838-compute@developer.gserviceaccount.com` | `roles/iam.serviceAccountUser` | Allow the deploy SA to act as the Cloud Run runtime SA (`actAs` permission required by `gcloud run deploy`) |

### Cross-project grants on `be-water-app`

The same SA deploys Be Water to its own project:

| Scope | Role | Why |
|-------|------|-----|
| project `be-water-app` | `roles/run.admin` | Deploy the `be-water` service |
| project `be-water-app` | `roles/artifactregistry.writer` | Push the `web` image to `be-water-docker` |
| repo `be-water-docker` | `roles/artifactregistry.repoAdmin` | Cleanup job deletes old digests (writer cannot delete) |
| runtime compute SA of `be-water-app` | `roles/iam.serviceAccountUser` | `actAs` for `gcloud run deploy` |

### How to reproduce from scratch

```bash
SA="biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com"
PROJECT="biwenger-tools"
COMPUTE_SA="319945089838-compute@developer.gserviceaccount.com"

# Project-level roles
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" --role="roles/run.developer"

# actAs on the runtime SA
gcloud iam service-accounts add-iam-policy-binding $COMPUTE_SA \
  --member="serviceAccount:$SA" --role="roles/iam.serviceAccountUser"
```

### Verify current permissions

```bash
# Project-level roles
gcloud projects get-iam-policy biwenger-tools \
  --flatten="bindings[].members" \
  --filter="bindings.members:biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com" \
  --format="table(bindings.role)"

# SA-level binding on compute SA
gcloud iam service-accounts get-iam-policy 319945089838-compute@developer.gserviceaccount.com \
  --format="table(bindings.role, bindings.members)"
```

## Branch protection on `master`

Configured via `gh api` (not visible in any repo file): required status checks
`Lint` + `Test` (from `ci.yml`), `enforce_admins` enabled, force-pushes and
branch deletion blocked. A direct push to `master` is rejected by GitHub for
everyone, admins included — every change goes branch → PR → green checks → merge.

Emergency escape hatch (CI outage blocking an urgent merge): temporarily lift
admin enforcement, merge, then re-enable —

```bash
gh api -X DELETE repos/jorgelillo7/lillorepo/branches/master/protection/enforce_admins
# ...merge...
gh api -X POST repos/jorgelillo7/lillorepo/branches/master/protection/enforce_admins
```
