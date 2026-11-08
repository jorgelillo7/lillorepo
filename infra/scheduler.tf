# The billing account's three free Scheduler jobs; a fourth costs $0.10 a month.
resource "google_cloud_scheduler_job" "daily_digest" {
  project          = local.biwenger
  region           = local.scheduler_region
  name             = "biwenger-daily-digest-trigger"
  description      = "Triggers biwenger-api /digests/daily — sends my squad + market PNGs to Telegram"
  schedule         = "15 7 * * *"
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

# Biwenger freezes the eleven at the round's first kick-off. Every quarter hour
# the API asks whether that kick-off is half an hour away and sets the lineup
# only then; every other tick reads the fixtures and returns. LaLiga kicks off
# from 12:00, so the ticks start at 10:00.
resource "google_cloud_scheduler_job" "kickoff_lineup" {
  project          = local.biwenger
  region           = local.scheduler_region
  name             = "biwenger-kickoff-lineup-trigger"
  description      = "Triggers biwenger-api /lineups/kickoff — sets the lineup 30 min before the round's first match"
  schedule         = "*/15 10-23 * * *"
  time_zone        = "Europe/Madrid"
  attempt_deadline = "180s"

  retry_config {
    retry_count          = 1
    max_backoff_duration = "60s"
    max_doublings        = 1
    max_retry_duration   = "0s"
    min_backoff_duration = "30s"
  }

  http_target {
    http_method = "POST"
    uri         = "https://biwenger-api-pjpqofuevq-no.a.run.app/lineups/kickoff"
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
