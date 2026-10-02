# Only the APIs the system calls. Defaults Google enables on every project
# (BigQuery, Dataplex, …) are left alone, and nothing is ever disabled by
# removing a line here.
locals {
  apis = {
    (local.biwenger) = [
      "artifactregistry.googleapis.com",
      "billingbudgets.googleapis.com",
      "cloudscheduler.googleapis.com",
      "drive.googleapis.com",
      "firestore.googleapis.com",
      "iam.googleapis.com",
      "iamcredentials.googleapis.com",
      "logging.googleapis.com",
      "run.googleapis.com",
      "secretmanager.googleapis.com",
      "sheets.googleapis.com",
      "storage.googleapis.com",
    ]
    (local.be_water) = [
      "artifactregistry.googleapis.com",
      "firestore.googleapis.com",
      "logging.googleapis.com",
      "run.googleapis.com",
      "secretmanager.googleapis.com",
      "storage.googleapis.com",
    ]
  }

  project_services = {
    for pair in flatten([
      for project, services in local.apis : [
        for service in services : { project = project, service = service }
      ]
    ]) : "${pair.project}/${pair.service}" => pair
  }
}

import {
  for_each = local.project_services
  to       = google_project_service.this[each.key]
  id       = each.key
}

resource "google_project_service" "this" {
  for_each = local.project_services

  project            = each.value.project
  service            = each.value.service
  disable_on_destroy = false
}
