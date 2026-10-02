# Both buckets sit in us-central1 on purpose: Cloud Storage's 5 GB always-free
# tier only exists in US regions.
import {
  to = google_storage_bucket.biwenger
  id = "${local.biwenger}/biwenger"
}

resource "google_storage_bucket" "biwenger" {
  project                     = local.biwenger
  name                        = "biwenger"
  location                    = "US-CENTRAL1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "inherited"

  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  lifecycle {
    prevent_destroy = true
  }
}

import {
  to = google_storage_bucket.be_water_photos
  id = "${local.be_water}/be-water-photos"
}

resource "google_storage_bucket" "be_water_photos" {
  project                     = local.be_water
  name                        = "be-water-photos"
  location                    = "US-CENTRAL1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "inherited"

  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  # Unreviewed uploads expire; approved photos live outside uploads/.
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age            = 30
      matches_prefix = ["uploads/"]
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Public read is granted through the legacy object-reader role. The legacy
# project-convenience roles and a league member's conditional upload grant on
# `biwenger` (special-tournaments/ only) are deliberately not managed here.
locals {
  bucket_iam = {
    for g in [
      { bucket = "biwenger", role = "roles/storage.legacyObjectReader", member = "allUsers" },
      { bucket = "biwenger", role = "roles/storage.objectUser", member = "serviceAccount:${local.sa.api}" },
      { bucket = "be-water-photos", role = "roles/storage.legacyObjectReader", member = "allUsers" },
      { bucket = "be-water-photos", role = "roles/storage.objectUser", member = "serviceAccount:${local.sa.be_water}" },
    ] : "b/${g.bucket} ${g.role} ${g.member}" => g
  }
}

import {
  for_each = local.bucket_iam
  to       = google_storage_bucket_iam_member.this[each.key]
  id       = each.key
}

resource "google_storage_bucket_iam_member" "this" {
  for_each = local.bucket_iam

  bucket = each.value.bucket
  role   = each.value.role
  member = each.value.member

  depends_on = [google_storage_bucket.biwenger, google_storage_bucket.be_water_photos]
}
