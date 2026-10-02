# Keyless GitHub Actions → GCP. The provider only admits tokens from this
# repository's master branch, which is what makes CI deploy-only.
resource "google_iam_workload_identity_pool" "github" {
  project                   = local.biwenger
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_iam_workload_identity_pool_provider" "github_oidc" {
  project                            = local.biwenger
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_condition = "assertion.repository == 'jorgelillo7/lillorepo' && assertion.ref == 'refs/heads/master'"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  lifecycle {
    prevent_destroy = true
  }
}
