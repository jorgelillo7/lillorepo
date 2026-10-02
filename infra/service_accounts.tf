# One identity per workload; the default compute accounts hold no role and are
# not managed here.
locals {
  service_accounts = {
    ci = {
      project      = local.biwenger
      account_id   = "biwenger-tools-sa"
      display_name = "biwenger-tools-sa"
    }
    api = {
      project      = local.biwenger
      account_id   = "run-biwenger-api"
      display_name = "Cloud Run: biwenger-api"
    }
    bot = {
      project      = local.biwenger
      account_id   = "run-biwenger-bot"
      display_name = "Cloud Run: biwenger-bot"
    }
    web = {
      project      = local.biwenger
      account_id   = "run-biwenger-web"
      display_name = "Cloud Run: biwenger-summary"
    }
    scraper = {
      project      = local.biwenger
      account_id   = "run-biwenger-scraper"
      display_name = "Cloud Run job: biwenger-scraper-data"
    }
    chucknorris = {
      project      = local.biwenger
      account_id   = "run-chucknorris-bot"
      display_name = "Cloud Run: chucknorris-bot"
    }
    scheduler = {
      project      = local.biwenger
      account_id   = "scheduler-invoker"
      display_name = "Cloud Scheduler: calls the api and runs the scraper"
    }
    be_water = {
      project      = local.be_water
      account_id   = "run-be-water"
      display_name = "Cloud Run: be-water"
    }
  }
}

resource "google_service_account" "this" {
  for_each = local.service_accounts

  project      = each.value.project
  account_id   = each.value.account_id
  display_name = each.value.display_name

  lifecycle {
    prevent_destroy = true
  }
}
