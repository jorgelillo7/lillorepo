# Containers and access only. Secret *values* never pass through Terraform —
# they would sit in the state file in clear. Versions are added by hand
# (docs/operations.md → "Updating a secret").
locals {
  secrets = {
    biwenger-secrets = {
      project   = local.biwenger
      accessors = [local.ci_sa, local.sa.api, local.sa.bot, local.sa.scraper, local.sa.web]
    }
    chucknorris-secrets = {
      project   = local.biwenger
      accessors = [local.ci_sa, local.sa.chucknorris]
    }
    be-water-secrets = {
      project   = local.be_water
      accessors = [local.sa.be_water]
    }
  }

  secret_iam = {
    for pair in flatten([
      for id, s in local.secrets : [
        for sa in s.accessors : { secret = id, project = s.project, member = "serviceAccount:${sa}" }
      ]
    ]) : "projects/${pair.project}/secrets/${pair.secret} roles/secretmanager.secretAccessor ${pair.member}" => pair
  }
}

import {
  for_each = local.secrets
  to       = google_secret_manager_secret.this[each.key]
  id       = "projects/${each.value.project}/secrets/${each.key}"
}

resource "google_secret_manager_secret" "this" {
  for_each = local.secrets

  project   = each.value.project
  secret_id = each.key

  replication {
    user_managed {
      replicas {
        location = local.region
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

import {
  for_each = local.secret_iam
  to       = google_secret_manager_secret_iam_member.this[each.key]
  id       = each.key
}

resource "google_secret_manager_secret_iam_member" "this" {
  for_each = local.secret_iam

  project   = each.value.project
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}
