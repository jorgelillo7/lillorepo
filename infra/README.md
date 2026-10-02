# infra — the static GCP layer as code

Terraform for the parts of both GCP projects (`biwenger-tools`, `be-water-app`)
that change rarely and break badly when they change by hand: identities,
grants, secrets, registries, buckets, Firestore settings, schedules, budgets.

Everything here was **adopted** from resources that already existed, through
`import` blocks. The first `apply` creates nothing and changes nothing; it only
writes the state.

## What is managed

| File | Resources |
|---|---|
| `apis.tf` | The APIs the system calls (never disabled on destroy) |
| `service_accounts.tf` | The seven runtime/CI identities and `run-be-water` |
| `iam.tf` | Project-level grants and service-account grants (actAs, WIF impersonation) |
| `workload_identity.tf` | Pool `github`, provider `github-oidc` (this repo, `master` only) |
| `artifact_registry.tf` | `biwenger-docker`, `be-water-docker`, CI's `repoAdmin` on each |
| `secrets.tf` | Secret **containers** and who may read them — never values |
| `storage.tf` | Buckets `biwenger` and `be-water-photos`, their public read and writers |
| `cloud_run_iam.tf` | Who may invoke each Cloud Run service and the scraper job |
| `scheduler.tf` | Daily digest and weekly scraper triggers (`europe-west1`) |
| `firestore.tf` | Both `(default)` databases, `messages` composite indexes, field overrides and the `bids.expires_at` TTL |
| `budgets.tf` | The three €1 monthly alerts on the billing account |

## What is deliberately not managed

- **Cloud Run services and the job themselves.** `deploy.yml` owns image,
  revision and environment; two owners of the same field is the classic IaC
  failure. Only their invoker grants are here.
- **Secret values.** They would sit in the state file in clear. Versions are
  added by hand — `docs/operations.md` → "Updating a secret".
- **Grants that are not the system's**: the owner's own roles, Google-managed
  service agents, the buckets' legacy project-convenience roles, and a league
  member's conditional upload grant on `biwenger` (`special-tournaments/`
  only). Every grant here is an additive `*_iam_member`, so all of those stay
  exactly as they are. Never switch to `*_iam_binding` or `*_iam_policy`: both
  are authoritative and would delete every member not listed.
- **Firestore documents** — data, not infrastructure.

Stateful resources (databases, indexes, buckets, secrets, registries, the WIF
pool and provider, service accounts) carry `prevent_destroy`: a change that
would force a replacement fails the `plan` instead of proposing one.

## Using it

Prerequisites: Terraform ≥ 1.16 and Application Default Credentials for an
owner of both projects (`gcloud auth application-default login`).

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # set billing_account
terraform init
terraform plan        # read-only
terraform apply       # owner only, locally
```

`terraform.tfvars` is gitignored — the billing account id stays off a public
repo. Budgets go through a second provider (`google.billing`) with a quota
project, because the Budget API refuses user credentials without one; every
other call needs no extra API enabled.

**Done** means `plan` reads `0 to add, 0 to change, 0 to destroy`. Once the
first `apply` has written the state, the import blocks have done their job and
can be deleted.

## State

`gs://lillorepo-tfstate/infra/` in `biwenger-tools`: us-central1 (always-free
tier), public access prevention enforced, versioned, keeping the ten most recent
previous versions — a bad `apply` is undone by restoring one. The state is a
single file of a few hundred KB, so the bucket never grows. It also holds the
lock that stops two applies from running at once.

The bucket is created by hand and deliberately absent from this configuration:
a config that manages the bucket holding its own state can delete it.

## Rules once adopted

- A managed resource changes **here**, in a PR, with the `plan` in the
  description — not with `gcloud`. A hand change shows up as drift on the next
  `plan` and will be reverted by the next `apply`.
- Only the owner applies. CI must never hold the IAM-admin rights an apply
  needs.
