locals {
  biwenger = "biwenger-tools"
  be_water = "be-water-app"

  biwenger_number = "319945089838"
  be_water_number = "1086466337948"

  region           = "europe-southwest1"
  scheduler_region = "europe-west1" # Cloud Scheduler is not offered in Madrid

  ci_sa = "biwenger-tools-sa@${local.biwenger}.iam.gserviceaccount.com"

  sa = {
    api         = "run-biwenger-api@${local.biwenger}.iam.gserviceaccount.com"
    bot         = "run-biwenger-bot@${local.biwenger}.iam.gserviceaccount.com"
    web         = "run-biwenger-web@${local.biwenger}.iam.gserviceaccount.com"
    scraper     = "run-biwenger-scraper@${local.biwenger}.iam.gserviceaccount.com"
    chucknorris = "run-chucknorris-bot@${local.biwenger}.iam.gserviceaccount.com"
    scheduler   = "scheduler-invoker@${local.biwenger}.iam.gserviceaccount.com"
    be_water    = "run-be-water@${local.be_water}.iam.gserviceaccount.com"
  }
}
