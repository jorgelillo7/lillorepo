# "¿Qué votáis?" (Android app com.jorgelillo.grouppolls, package packages/group_polls):
# its own GCP/Firebase project, Firestore in Madrid like the other two, and the security rules,
# which are the app's only backend logic.
#
# Off until the project exists: with `group_polls` empty every resource below has zero instances,
# so plan and apply do nothing. Turning it on: packages/group_polls/OPERATIONS.md → "Create the
# project" (create it by hand, then set the id here and import the database).
#
# Not managed here, set by hand in the Firebase console (no stable Terraform resource for them):
# anonymous sign-in (Authentication) and App Check enforcement on Firestore.
locals {
  group_polls = "" # e.g. "que-votais-app" once created

  group_polls_projects = local.group_polls == "" ? toset([]) : toset([local.group_polls])

  group_polls_apis = local.group_polls == "" ? toset([]) : toset([
    "firebase.googleapis.com",
    "firebaseappcheck.googleapis.com",
    "firebaserules.googleapis.com",
    "firestore.googleapis.com",
    "identitytoolkit.googleapis.com",
  ])
}

resource "google_project_service" "group_polls" {
  for_each = local.group_polls_apis

  project            = local.group_polls
  service            = each.key
  disable_on_destroy = false
}

resource "google_firestore_database" "group_polls" {
  for_each = local.group_polls_projects

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

# The public feed: visibility == "public", hidden == false, createdAt in the last week, newest first.
resource "google_firestore_index" "group_polls_feed" {
  for_each = local.group_polls_projects

  project     = each.key
  database    = google_firestore_database.group_polls[each.key].name
  collection  = "polls"
  query_scope = "COLLECTION"

  fields {
    field_path = "visibility"
    order      = "ASCENDING"
  }
  fields {
    field_path = "hidden"
    order      = "ASCENDING"
  }
  fields {
    field_path = "createdAt"
    order      = "DESCENDING"
  }
}

# "Delete my data" finds a user's votes across polls: collection-group query on voterId.
resource "google_firestore_field" "group_polls_votes_voter" {
  for_each = local.group_polls_projects

  project    = each.key
  database   = google_firestore_database.group_polls[each.key].name
  collection = "votes"
  field      = "voterId"

  index_config {
    indexes {
      order       = "ASCENDING"
      query_scope = "COLLECTION_GROUP"
    }
  }
}

resource "google_firebaserules_ruleset" "group_polls" {
  for_each = local.group_polls_projects

  project = each.key
  source {
    files {
      name    = "firestore.rules"
      content = file("${path.module}/../packages/group_polls/firestore.rules")
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_firebaserules_release" "group_polls" {
  for_each = local.group_polls_projects

  project      = each.key
  name         = "cloud.firestore"
  ruleset_name = google_firebaserules_ruleset.group_polls[each.key].name
}
