# Two of the billing account's three free Scheduler jobs.
import {
  to = google_cloud_scheduler_job.daily_digest
  id = "projects/${local.biwenger}/locations/${local.scheduler_region}/jobs/biwenger-daily-digest-trigger"
}

resource "google_cloud_scheduler_job" "daily_digest" {
  project          = local.biwenger
  region           = local.scheduler_region
  name             = "biwenger-daily-digest-trigger"
  description      = "Triggers biwenger-api /digests/daily — sends my squad + market PNGs to Telegram"
  schedule         = "0 9 * * *"
  time_zone        = "Europe/Madrid"
  attempt_deadline = "180s"

  retry_config {
    max_backoff_duration = "3600s"
    max_doublings        = 5
    max_retry_duration   = "0s"
    min_backoff_duration = "5s"
  }

  http_target {
    http_method = "POST"
    uri         = "https://biwenger-api-pjpqofuevq-no.a.run.app/digests/daily"
    body        = base64encode("{}")
    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = local.sa.scheduler
      audience              = "https://biwenger-api-pjpqofuevq-no.a.run.app"
    }
  }
}

import {
  to = google_cloud_scheduler_job.weekly_scraper
  id = "projects/${local.biwenger}/locations/${local.scheduler_region}/jobs/biwenger-scraper-data-scheduler-trigger"
}

# Runs the Cloud Run job through the Admin API, hence OAuth rather than OIDC.
resource "google_cloud_scheduler_job" "weekly_scraper" {
  project          = local.biwenger
  region           = local.scheduler_region
  name             = "biwenger-scraper-data-scheduler-trigger"
  schedule         = "0 22 * * 0"
  time_zone        = "Europe/Madrid"
  attempt_deadline = "180s"

  retry_config {
    max_backoff_duration = "3600s"
    max_doublings        = 5
    max_retry_duration   = "0s"
    min_backoff_duration = "5s"
  }

  http_target {
    http_method = "POST"
    uri         = "https://${local.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${local.biwenger}/jobs/biwenger-scraper-data:run"

    oauth_token {
      service_account_email = local.sa.scheduler
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
}
