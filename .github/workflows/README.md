# CI/CD — deploy.yml

Workflow that runs on every push to `master` when files under `core/`, `packages/biwenger_tools/`, `tools/`, or `.github/workflows/` change.

## Stages

```
Run tests → Deploy web app ─┐
                             ├→ Clean up old images
           Deploy scraper ──┘
```

1. **Run tests** — `bazel test` for all three modules (web, scraper_job, core).
2. **Deploy web app** — builds and pushes the OCI image, then deploys to the `biwenger-summary` Cloud Run service.
3. **Deploy scraper job** — builds and pushes the OCI image, then updates the `biwenger-scraper-data` Cloud Run Job.
4. **Clean up old images** — runs `scripts/clean-images-artifact.sh` to prune stale images from Artifact Registry.

## Required GitHub secrets

| Secret | Description |
|--------|-------------|
| `GCP_SA_KEY` | JSON key of the `biwenger-tools-sa` service account |
| `GDRIVE_FOLDER_ID` | Google Drive folder ID for CSV storage |
| `SECRET_KEY` | Flask session secret key |
| `ADMIN_PASSWORD` | Admin panel password |
| `LIGAS_ESPECIALES_SHEET_ID_25_26` | Google Sheets ID (ligas especiales 25-26) |
| `LIGAS_ESPECIALES_SHEET_ID_24_25` | Google Sheets ID (ligas especiales 24-25) |
| `TROFEOS_SHEET_ID_25_26` | Google Sheets ID (trofeos 25-26) |
| `COMUNICADOS_CSV_URL` | Public Drive URL for comunicados CSV |
| `PALMARES_CSV_URL` | Public Drive URL for palmarés CSV |
| `PARTICIPACION_CSV_URL` | Public Drive URL for participación CSV |

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
