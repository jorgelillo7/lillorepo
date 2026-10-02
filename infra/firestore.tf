# Settings, composite indexes and single-field overrides. Documents are data,
# not infrastructure, and never appear here.
locals {
  firestore_projects = toset([local.biwenger, local.be_water])
}

import {
  for_each = local.firestore_projects
  to       = google_firestore_database.default[each.key]
  id       = "projects/${each.key}/databases/(default)"
}

resource "google_firestore_database" "default" {
  for_each = local.firestore_projects

  project                           = each.key
  name                              = "(default)"
  location_id                       = local.region
  type                              = "FIRESTORE_NATIVE"
  concurrency_mode                  = "PESSIMISTIC"
  app_engine_integration_mode       = "DISABLED"
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_DISABLED"
  delete_protection_state           = "DELETE_PROTECTION_ENABLED"
  deletion_policy                   = "ABANDON"

  lifecycle {
    prevent_destroy = true
  }
}

# messages by category, newest first and oldest first (cursor pagination).
locals {
  messages_indexes = {
    by_categoria_fecha_desc = { id = "CICAgOjXh4EK", order = "DESCENDING" }
    by_categoria_fecha_asc  = { id = "CICAgJiUpoMK", order = "ASCENDING" }
  }
}

import {
  for_each = local.messages_indexes
  to       = google_firestore_index.messages[each.key]
  id       = "projects/${local.biwenger}/databases/(default)/collectionGroups/messages/indexes/${each.value.id}"
}

resource "google_firestore_index" "messages" {
  for_each = local.messages_indexes

  project     = local.biwenger
  database    = google_firestore_database.default[local.biwenger].name
  collection  = "messages"
  query_scope = "COLLECTION"

  fields {
    field_path = "categoria"
    order      = "ASCENDING"
  }
  fields {
    field_path = "fecha"
    order      = each.value.order
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Fields exempt from single-field indexing (large or never queried), plus the
# TTL on bids.expires_at.
locals {
  field_overrides = {
    "messages.contenido" = { project = local.biwenger, collection = "messages", field = "contenido", ttl = false }
    "entries.entry"      = { project = local.biwenger, collection = "entries", field = "entry", ttl = false }
    "bids.expires_at"    = { project = local.biwenger, collection = "bids", field = "expires_at", ttl = true }
    "water_revisions.previous" = {
      project = local.be_water, collection = "water_revisions", field = "previous", ttl = false
    }
  }
}

import {
  for_each = local.field_overrides
  to       = google_firestore_field.override[each.key]
  id       = "projects/${each.value.project}/databases/(default)/collectionGroups/${each.value.collection}/fields/${each.value.field}"
}

resource "google_firestore_field" "override" {
  for_each = local.field_overrides

  project    = each.value.project
  database   = google_firestore_database.default[each.value.project].name
  collection = each.value.collection
  field      = each.value.field

  index_config {}

  dynamic "ttl_config" {
    for_each = each.value.ttl ? [1] : []
    content {}
  }
}
