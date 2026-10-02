# Every grant is an additive *_iam_member: Terraform owns exactly the lines
# below and nothing else in each policy. Service agents, the owner's own roles
# and grants to people outside the project stay out of the code and are never
# touched by an apply. Never switch these to *_iam_binding or *_iam_policy —
# either would delete every member not listed here.
#
# Each map key is the resource's import id (`terraform import` by hand).

locals {
  project_iam = {
    for g in [
      { project = local.biwenger, role = "roles/artifactregistry.writer", member = "serviceAccount:${local.ci_sa}" },
      { project = local.biwenger, role = "roles/run.developer", member = "serviceAccount:${local.ci_sa}" },
      { project = local.biwenger, role = "roles/viewer", member = "serviceAccount:${local.ci_sa}" },
      { project = local.biwenger, role = "roles/datastore.user", member = "serviceAccount:${local.sa.api}" },
      { project = local.biwenger, role = "roles/datastore.user", member = "serviceAccount:${local.sa.scraper}" },
      { project = local.biwenger, role = "roles/datastore.viewer", member = "serviceAccount:${local.sa.web}" },
      { project = local.be_water, role = "roles/artifactregistry.writer", member = "serviceAccount:${local.ci_sa}" },
      { project = local.be_water, role = "roles/run.admin", member = "serviceAccount:${local.ci_sa}" },
      { project = local.be_water, role = "roles/datastore.user", member = "serviceAccount:${local.sa.be_water}" },
    ] : "${g.project} ${g.role} ${g.member}" => g
  }

  # CI deploys every service as its own runtime identity (actAs), and GitHub
  # Actions on this repository may impersonate the CI account.
  service_account_iam = {
    for g in concat(
      [
        for key in ["api", "bot", "web", "scraper", "chucknorris", "be_water"] : {
          sa     = local.sa[key]
          role   = "roles/iam.serviceAccountUser"
          member = "serviceAccount:${local.ci_sa}"
        }
      ],
      [{
        sa     = local.ci_sa
        role   = "roles/iam.workloadIdentityUser"
        member = "principalSet://iam.googleapis.com/projects/${local.biwenger_number}/locations/global/workloadIdentityPools/github/attribute.repository/jorgelillo7/lillorepo"
      }],
    ) : "projects/${regex("@([^.]+)\\.", g.sa)[0]}/serviceAccounts/${g.sa} ${g.role} ${g.member}" => g
  }
}

resource "google_project_iam_member" "this" {
  for_each = local.project_iam

  project = each.value.project
  role    = each.value.role
  member  = each.value.member
}

resource "google_service_account_iam_member" "this" {
  for_each = local.service_account_iam

  service_account_id = split(" ", each.key)[0]
  role               = each.value.role
  member             = each.value.member
}
