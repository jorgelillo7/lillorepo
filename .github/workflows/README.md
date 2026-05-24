# CI/CD — deploy.yml

Workflow that runs on every push to `master` when files under `core/`, `packages/`, `tools/`, `docker/`, `MODULE.bazel` or `.github/workflows/` change.

## Stages

```
Lint → Detect changed modules → Run tests ─┬→ Deploy web ────────────┐
                                            ├→ Deploy scraper ────────┤
                                            ├→ Deploy api ────────────┼→ Clean up old images
                                            ├→ Deploy bot ────────────┤
                                            └→ Deploy chucknorris_bot ┘
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
5. **Clean up old images** — runs `scripts/clean-images-artifact.sh` to prune stale digests from Artifact Registry.

## Required GitHub secrets

| Secret | Description |
|--------|-------------|
| `GCP_SA_KEY` | JSON key of the `biwenger-tools-sa` service account |
| `SECRET_KEY` | Flask session secret key |
| `ADMIN_PASSWORD` | Admin panel password |
| `LIGAS_ESPECIALES_SHEET_ID_25_26` | Google Sheets ID (ligas especiales 25-26) |
| `LIGAS_ESPECIALES_SHEET_ID_24_25` | Google Sheets ID (ligas especiales 24-25) |
| `TROFEOS_SHEET_ID_25_26` | Google Sheets ID (trofeos 25-26) |

Other credentials (Biwenger login, Telegram bot tokens, JP token) live in Secret Manager and are injected at runtime via `--update-secrets`, not as GitHub secrets.

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
