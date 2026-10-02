# A read-only identity for `terraform plan` in GitHub Actions: on pull requests
# touching infra/ and in the weekly drift check. Apply stays local, by the owner.
#
# Its own pool, not a provider in `github`: the deploy account's
# workloadIdentityUser grant matches attribute.repository across the whole
# `github` pool, so a provider there that admits pull requests would hand
# every PR the deploy identity.

resource "google_iam_workload_identity_pool" "github_plan" {
  project                   = local.biwenger
  workload_identity_pool_id = "github-plan"
  display_name              = "GitHub Actions: terraform plan"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_iam_workload_identity_pool_provider" "github_plan" {
  project                            = local.biwenger
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_plan.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-plan"
  display_name                       = "GitHub OIDC: infra.yml"

  # Any ref, but only this repository's infra workflow. Fork PRs receive no
  # OIDC token at all.
  attribute_condition = "assertion.repository == 'jorgelillo7/lillorepo' && assertion.workflow_ref.startsWith('jorgelillo7/lillorepo/.github/workflows/infra.yml@')"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "terraform_plan" {
  project      = local.biwenger
  account_id   = "terraform-plan"
  display_name = "GitHub Actions: terraform plan (read-only)"
}

resource "google_service_account_iam_member" "terraform_plan_wif" {
  service_account_id = google_service_account.terraform_plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_plan.name}/attribute.repository/jorgelillo7/lillorepo"
}

# Viewer reads every resource's configuration (and Firestore documents, which
# plan never asks for); securityReviewer adds the IAM policies Viewer misses.
# Neither can read a secret's value or change anything.
locals {
  terraform_plan_roles = {
    for pair in setproduct(
      [local.biwenger, local.be_water],
      ["roles/viewer", "roles/iam.securityReviewer"],
    ) : "${pair[0]} ${pair[1]}" => { project = pair[0], role = pair[1] }
  }
}

resource "google_project_iam_member" "terraform_plan" {
  for_each = local.terraform_plan_roles

  project = each.value.project
  role    = each.value.role
  member  = google_service_account.terraform_plan.member
}

# The budgets provider bills its calls to biwenger-tools.
resource "google_project_iam_member" "terraform_plan_quota" {
  project = local.biwenger
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = google_service_account.terraform_plan.member
}

resource "google_billing_account_iam_member" "terraform_plan" {
  billing_account_id = var.billing_account
  role               = "roles/billing.viewer"
  member             = google_service_account.terraform_plan.member

  depends_on = [google_project_service.this]
}

# The state bucket is created by hand and not managed here; only this read
# grant on it is. CI plans with -lock=false, so it never writes.
resource "google_storage_bucket_iam_member" "terraform_plan_state" {
  bucket = "lillorepo-tfstate"
  role   = "roles/storage.objectViewer"
  member = google_service_account.terraform_plan.member
}
