locals {
  docker_repos = {
    biwenger = {
      project     = local.biwenger
      id          = "biwenger-docker"
      description = "Docker images for Biwenger Tools"
    }
    be_water = {
      project     = local.be_water
      id          = "be-water-docker"
      description = null
    }
  }
}

# Old digests are pruned by deploy.yml's cleanup job, not by repository
# cleanup policies.
resource "google_artifact_registry_repository" "docker" {
  for_each = local.docker_repos

  project       = each.value.project
  location      = local.region
  repository_id = each.value.id
  format        = "DOCKER"
  description   = each.value.description

  lifecycle {
    prevent_destroy = true
  }
}

# repoAdmin lets the CI cleanup job delete digests; the project-level
# artifactregistry.writer only pushes.
locals {
  docker_repo_iam = {
    for key, repo in local.docker_repos :
    "projects/${repo.project}/locations/${local.region}/repositories/${repo.id} roles/artifactregistry.repoAdmin serviceAccount:${local.ci_sa}" => key
  }
}

resource "google_artifact_registry_repository_iam_member" "this" {
  for_each = local.docker_repo_iam

  project    = local.docker_repos[each.value].project
  location   = local.region
  repository = local.docker_repos[each.value].id
  role       = "roles/artifactregistry.repoAdmin"
  member     = "serviceAccount:${local.ci_sa}"
}
