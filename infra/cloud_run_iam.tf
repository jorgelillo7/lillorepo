# Who may call each service and job. The services and the job themselves are
# owned by deploy.yml (image, revision, env) and are not managed here; only
# their invoker grants are.
locals {
  run_service_iam = {
    for g in [
      { project = local.biwenger, name = "biwenger-api", member = "serviceAccount:${local.sa.bot}" },
      { project = local.biwenger, name = "biwenger-api", member = "serviceAccount:${local.sa.scheduler}" },
      { project = local.biwenger, name = "biwenger-bot", member = "allUsers" },
      { project = local.biwenger, name = "biwenger-summary", member = "allUsers" },
      { project = local.biwenger, name = "chucknorris-bot", member = "allUsers" },
      { project = local.be_water, name = "be-water", member = "allUsers" },
    ] : "projects/${g.project}/locations/${local.region}/services/${g.name} roles/run.invoker ${g.member}" => g
  }

  run_job_iam = {
    for g in [
      { name = "biwenger-scraper-data", member = "serviceAccount:${local.sa.api}" },
      { name = "biwenger-scraper-data", member = "serviceAccount:${local.sa.web}" },
      { name = "biwenger-scraper-data", member = "serviceAccount:${local.sa.scheduler}" },
    ] : "projects/${local.biwenger}/locations/${local.region}/jobs/${g.name} roles/run.invoker ${g.member}" => g
  }
}

import {
  for_each = local.run_service_iam
  to       = google_cloud_run_v2_service_iam_member.invoker[each.key]
  id       = each.key
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = local.run_service_iam

  project  = each.value.project
  location = local.region
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = each.value.member
}

import {
  for_each = local.run_job_iam
  to       = google_cloud_run_v2_job_iam_member.invoker[each.key]
  id       = each.key
}

resource "google_cloud_run_v2_job_iam_member" "invoker" {
  for_each = local.run_job_iam

  project  = local.biwenger
  location = local.region
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = each.value.member
}
